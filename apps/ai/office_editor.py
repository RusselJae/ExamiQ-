"""ONLYOFFICE Document Server integration for editing learning materials.

The embedded editor round-trips the *binary* file, which is why it is worth
running alongside the built-in HTML editor rather than instead of it: a Word
file edited in ONLYOFFICE keeps its real styles, headers and tables, whereas
the HTML editor can only carry the subset that maps onto browser tags.

Security notes:
  * Every payload crossing the Document Server boundary is JWT-signed.
  * ``download_edited_document`` only fetches from the configured Document
    Server origin, so a crafted callback URL cannot be used to probe the
    internal network (SSRF).
  * The file URL handed to the Document Server carries a short-lived signed
    token, so the Document Server can fetch it without a session cookie.
"""

from __future__ import annotations

import logging
import posixpath
from urllib.parse import urlparse

import jwt
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.signing import BadSignature, TimestampSigner
from django.utils import timezone

from apps.ai.models import LearningDocument

logger = logging.getLogger(__name__)

# ONLYOFFICE command codes we care about.
STATUS_EDITING = 1
STATUS_READY_FOR_SAVE = 2
STATUS_CLOSED_UNCHANGED = 3
STATUS_CLOSED_CHANGED = 4
STATUS_FORCE_SAVE = 6
STATUS_ERROR = 7

# Only these statuses carry a new file to store.
_SAVING_STATUSES = frozenset({STATUS_READY_FOR_SAVE, STATUS_FORCE_SAVE})

# Signed-file token lifetime. The Document Server fetches immediately, so this
# only needs to survive a slow start-up, not a long editing session.
FILE_TOKEN_MAX_AGE_SECONDS = 60 * 60

MAX_EDITED_FILE_BYTES = 64 * 1024 * 1024


class OfficeEditorError(ValueError):
    """Raised when ONLYOFFICE is misconfigured or a payload is rejected."""


def is_configured() -> bool:
    return bool(getattr(settings, "ONLYOFFICE_DOCUMENT_SERVER_URL", ""))


def _jwt_enabled() -> bool:
    return bool(
        getattr(settings, "ONLYOFFICE_JWT_ENABLED", True)
        and getattr(settings, "ONLYOFFICE_JWT_SECRET", "")
    )


def server_url() -> str:
    url = getattr(settings, "ONLYOFFICE_DOCUMENT_SERVER_URL", "") or ""
    return url.rstrip("/")


def api_script_url() -> str:
    """URL of the browser-side ONLYOFFICE loader."""
    return f"{server_url()}/web-apps/apps/api/documents/api.js"


def is_editable(document: LearningDocument) -> bool:
    """True when the Document Server can reflow-edit this document."""
    if not is_configured():
        return False
    if not document.file:
        return False
    name = (document.original_name or "").lower()
    allowed = getattr(settings, "ONLYOFFICE_EDITABLE_SUFFIXES", ())
    return name.endswith(tuple(allowed))


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def sign_payload(payload: dict) -> dict:
    """Return the payload with a ``token`` field ONLYOFFICE accepts."""
    if not _jwt_enabled():
        return payload
    try:
        token = jwt.encode(
            payload,
            settings.ONLYOFFICE_JWT_SECRET,
            algorithm="HS256",
        )
    except Exception as exc:  # pragma: no cover - misconfiguration
        raise OfficeEditorError(f"Could not sign ONLYOFFICE token: {exc}") from exc
    return {**payload, "token": token}


def verify_payload(payload: dict) -> dict:
    """Verify and return the callback body, rejecting unsigned/invalid tokens."""
    if not _jwt_enabled():
        return payload
    token = (payload or {}).get("token")
    if not token:
        raise OfficeEditorError("ONLYOFFICE callback is missing its token.")
    try:
        return jwt.decode(
            token,
            settings.ONLYOFFICE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError as exc:
        raise OfficeEditorError("Invalid ONLYOFFICE token.") from exc


# --------------------------------------------------------------------------- #
# Signed file access
# --------------------------------------------------------------------------- #
def file_token(document: LearningDocument) -> str:
    signer = TimestampSigner(salt="onlyoffice.material")
    return signer.sign(f"{document.pk}:{document.file.name}")


def document_from_token(token: str) -> LearningDocument | None:
    """Resolve a signed file token back to its document, or None."""
    if not token:
        return None
    signer = TimestampSigner(salt="onlyoffice.material")
    try:
        value = signer.unsign(token, max_age=FILE_TOKEN_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    pk, _, stored_name = value.partition(":")
    if not pk.isdigit():
        return None
    document = (
        LearningDocument.objects.filter(pk=int(pk))
        .select_related("subject")
        .first()
    )
    # The token is bound to the exact stored path, so replacing the file
    # invalidates older tokens.
    if document is None or document.file.name != stored_name:
        return None
    return document


# --------------------------------------------------------------------------- #
# Editor configuration
# --------------------------------------------------------------------------- #
def railway_public_base_url() -> str:
    """The app's own public origin when it runs on Railway.

    Railway exposes every service on ``*.up.railway.app``; that origin is the
    only one the Document Server can reliably reach.
    """
    import os

    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        if "://" not in domain:
            domain = f"https://{domain}"
        return domain.rstrip("/")

    static_url = os.environ.get("RAILWAY_STATIC_URL", "").strip()
    if static_url:
        return static_url.rstrip("/")
    return ""


def is_local_host(host: str) -> bool:
    """True for hosts the Document Server can never reach."""
    host = (host or "").split(":")[0].strip().lower()
    if not host:
        return True
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


# Dev tunnels expire, so a URL pointing at one is never a valid public origin
# for a deployed app.
_TUNNEL_HOSTS = (
    ".ngrok.io",
    ".ngrok-free.dev",
    ".ngrok.app",
    ".trycloudflare.com",
    ".loca.lt",
    ".localtunnel.me",
    ".serveo.net",
)


def is_tunnel_host(host: str) -> bool:
    """True for short-lived development tunnel hosts."""
    host = (host or "").split(":")[0].strip().lower()
    return any(host.endswith(suffix) for suffix in _TUNNEL_HOSTS)


def public_base_url() -> str:
    """Public origin the Document Server should use to reach this app.

    The Document Server fetches files and posts save callbacks server-to-server,
    so it cannot use the request's host when that is a private address such as
    ``127.0.0.1``. Set ``ONLYOFFICE_PUBLIC_BASE_URL`` (e.g. an ngrok tunnel) to
    override; otherwise the request host is used.

    On Railway the app's public domain wins: a tunnel URL copied from a local
    ``.env`` (ngrok tunnels expire) would otherwise leave the Document Server
    unable to download the file, and the editor silently never renders.
    """
    configured = (getattr(settings, "ONLYOFFICE_PUBLIC_BASE_URL", "") or "").strip()

    railway = railway_public_base_url()
    if railway:
        if not configured:
            return railway
        from urllib.parse import urlparse

        configured_host = urlparse(configured).hostname or ""
        if is_local_host(configured_host) or is_tunnel_host(configured_host):
            logger.warning(
                "ONLYOFFICE_PUBLIC_BASE_URL points at %s, which the Document "
                "Server cannot use for a deployed app. Using %s instead.",
                configured,
                railway,
            )
            return railway
        if configured_host != urlparse(railway).hostname:
            logger.warning(
                "ONLYOFFICE_PUBLIC_BASE_URL is %s but the app is served from %s. "
                "The Document Server may not be able to reach this app.",
                configured,
                railway,
            )
        return configured.rstrip("/")

    return configured.rstrip("/")


def absolute_url(request, path: str) -> str:
    """Build a Document-Server-facing absolute URL, honouring the override."""
    base = public_base_url()
    if base:
        return f"{base}{path}"
    return request.build_absolute_uri(path)


def document_key(document: LearningDocument) -> str:
    """Cache key for the Document Server.

    Changing the stored file must change this, otherwise ONLYOFFICE replays a
    stale cached conversion. Microsecond resolution matters: a professor can
    save and reopen inside the same second, and a whole-second key would
    collide and hand back the pre-edit conversion.
    """
    try:
        modified = int(document.updated.timestamp() * 1_000_000)
    except (AttributeError, OSError, ValueError, OverflowError):
        modified = 0
    return f"{document.pk}-{modified}"


def build_editor_config(
    document: LearningDocument,
    *,
    user,
    file_url: str,
    callback_url: str,
) -> dict:
    """Build the config object the ONLYOFFICE Docs API expects."""
    if not is_configured():
        raise OfficeEditorError("ONLYOFFICE is not configured.")
    if not document.file:
        raise OfficeEditorError("This material has no stored file.")

    name = document.original_name or document.display_title or f"material-{document.pk}"
    payload = {
        "documentType": "word",
        "document": {
            "fileType": posixpath.splitext(name)[1].lstrip(".").lower() or "docx",
            "key": document_key(document),
            "title": document.display_title,
            "url": file_url,
            "permissions": {
                "edit": True,
                "download": True,
                "print": True,
            },
        },
        "editorConfig": {
            "mode": "edit",
            "lang": "en",
            "callbackUrl": callback_url,
            "user": {
                "id": str(user.pk),
                "name": user.get_full_name() or user.get_username(),
            },
        },
    }
    return sign_payload(payload)


# --------------------------------------------------------------------------- #
# Saving the edited file back
# --------------------------------------------------------------------------- #
def _same_origin(url: str) -> bool:
    """True when ``url`` points at the configured Document Server host."""
    target = urlparse(url)
    expected = urlparse(server_url())
    if not expected.netloc:
        return False
    return (target.scheme, target.netloc) == (expected.scheme, expected.netloc)


def download_edited_document(document: LearningDocument, url: str) -> bytes:
    """Fetch the edited file from the Document Server.

    Only URLs on the Document Server origin are accepted, which stops the
    callback from being turned into an SSRF proxy.
    """
    import requests

    if not url:
        raise OfficeEditorError("ONLYOFFICE callback did not include a file URL.")
    if not _same_origin(url):
        raise OfficeEditorError("Refusing to download from an untrusted host.")

    try:
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OfficeEditorError(f"Could not download the edited file: {exc}") from exc

    payload = bytearray()
    for block in response.iter_content(chunk_size=65536):
        payload.extend(block)
        if len(payload) > MAX_EDITED_FILE_BYTES:
            raise OfficeEditorError("The edited file is unexpectedly large.")
    if not payload:
        raise OfficeEditorError("The Document Server returned an empty file.")
    return bytes(payload)


def store_edited_document(document: LearningDocument, payload: bytes) -> None:
    """Overwrite the stored file in place, keeping its path stable."""
    basename = posixpath.basename(document.file.name) or "material.docx"
    document.file.delete(save=False)
    document.file.save(basename, ContentFile(payload), save=True)
    document.updated = timezone.now()
    document.save(update_fields=["file", "updated"])
    logger.info(
        "Stored ONLYOFFICE edit for document %s (%s bytes)",
        document.pk,
        len(payload),
    )


__all__ = [
    "MAX_EDITED_FILE_BYTES",
    "OfficeEditorError",
    "absolute_url",
    "api_script_url",
    "build_editor_config",
    "default_storage",
    "document_from_token",
    "document_key",
    "download_edited_document",
    "file_token",
    "is_configured",
    "is_editable",
    "server_url",
    "sign_payload",
    "store_edited_document",
    "verify_payload",
]
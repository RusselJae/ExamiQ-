"""Signup email OTP generation, delivery, and verification."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.models import EmailSignupOTP, User

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
SIGNUP_OTP_SESSION_KEY = "signup_otp_user_id"
RESEND_API_URL = "https://api.resend.com/emails"
# Inactive accounts that never finished email OTP are removed after this window.
ABANDONED_SIGNUP_RETENTION = timedelta(hours=24)


class SignupOTPError(Exception):
    """Raised when OTP send/verify fails with a user-facing message."""


def _hash_code(code: str) -> str:
    material = f"{settings.SECRET_KEY}:signup-otp:{code}".encode()
    return hashlib.sha256(material).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _resend_api_key() -> str:
    """Return Resend API key from dedicated setting or SMTP password fallback."""
    key = (getattr(settings, "RESEND_API_KEY", None) or "").strip()
    if key:
        return key
    password = (getattr(settings, "EMAIL_HOST_PASSWORD", None) or "").strip()
    if password.startswith("re_"):
        return password
    return ""


def _should_use_resend_api() -> bool:
    """Prefer HTTPS Resend API when configured (avoids PaaS SMTP timeouts)."""
    if not _resend_api_key():
        return False
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    return not (
        "locmem" in backend or "console" in backend or "dummy" in backend
    )


def _send_via_resend_api(
    *,
    subject: str,
    text_body: str,
    html_body: str,
    to_email: str,
) -> None:
    """Send email through Resend's HTTPS API (SDK; avoids Cloudflare 1010 on urllib)."""
    api_key = _resend_api_key()
    payload = {
        "from": settings.DEFAULT_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    try:
        import resend
        from resend.exceptions import ResendError
    except ImportError:
        logger.warning("resend package missing; falling back to urllib")
        _send_via_resend_urllib(api_key=api_key, payload=payload)
        return

    resend.api_key = api_key
    try:
        result = resend.Emails.send(payload)
    except ResendError as exc:
        logger.warning("Resend SDK error: %s", exc)
        raise SignupOTPError(
            "We could not send the verification email. Check Resend API settings."
        ) from exc
    except (OSError, TimeoutError, ConnectionError) as exc:
        logger.warning("Resend SDK transport error: %s", exc)
        raise SignupOTPError(
            "We could not send the verification email. Please try again shortly."
        ) from exc

    if isinstance(result, dict) and result.get("statusCode", 200) >= 400:
        logger.warning("Resend SDK rejected send: %s", result)
        raise SignupOTPError(
            "We could not send the verification email. Check Resend API settings."
        )


def _send_via_resend_urllib(*, api_key: str, payload: dict) -> None:
    """urllib fallback with an explicit User-Agent (Cloudflare-friendly)."""
    timeout = int(getattr(settings, "EMAIL_TIMEOUT", 15) or 15)
    request = urllib.request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ExamiQ/1.0 (+https://examiq.xyz; Django OTP)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise SignupOTPError(
                    "We could not send the verification email. Please try again."
                )
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}
            detail = str(data.get("message") or data.get("error") or body)[:200]
        except (TypeError, ValueError, AttributeError, OSError, json.JSONDecodeError):
            detail = str(exc.reason or exc)
        logger.warning("Resend API HTTP %s: %s", exc.code, detail)
        raise SignupOTPError(
            "We could not send the verification email. Check Resend API settings."
        ) from exc
    except urllib.error.URLError as exc:
        logger.warning("Resend API network error: %s", exc.reason)
        raise SignupOTPError(
            "We could not reach the email service. Please try again shortly."
        ) from exc
    except TimeoutError as exc:
        logger.warning("Resend API timed out")
        raise SignupOTPError(
            "Sending the verification email timed out. Please try again."
        ) from exc


def _deliver_otp_email(
    *,
    subject: str,
    text_body: str,
    html_body: str,
    to_email: str,
) -> None:
    """Deliver OTP via Resend HTTPS API when configured, else Django email backend."""
    if _should_use_resend_api():
        _send_via_resend_api(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            to_email=to_email,
        )
        return
    send_mail(
        subject,
        text_body,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
        html_message=html_body,
    )


def send_signup_otp(user: User, *, force: bool = False) -> EmailSignupOTP:
    """Create (or replace) an OTP for ``user`` and email it."""
    now = timezone.now()
    active = (
        EmailSignupOTP.objects.filter(user=user, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if active and not force and now - active.last_sent_at < OTP_RESEND_COOLDOWN:
        wait = int(
            (OTP_RESEND_COOLDOWN - (now - active.last_sent_at)).total_seconds()
        )
        raise SignupOTPError(
            f"Please wait {max(wait, 1)} seconds before requesting a new code."
        )

    EmailSignupOTP.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=now
    )

    code = _generate_code()
    otp = EmailSignupOTP.objects.create(user=user, code_hash=_hash_code(code))

    subject = "Your ExamiQ verification code"
    context = {
        "user": user,
        "code": code,
        "minutes": int(OTP_TTL.total_seconds() // 60),
    }
    text_body = render_to_string("emails/signup_otp.txt", context)
    html_body = render_to_string("emails/signup_otp.html", context)
    _deliver_otp_email(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to_email=user.email,
    )
    return otp


def verify_signup_otp(user: User, code: str) -> User:
    """Validate an email OTP and activate only already-approved accounts."""
    cleaned = (code or "").strip()
    if not cleaned.isdigit() or len(cleaned) != OTP_LENGTH:
        raise SignupOTPError("Enter the 6-digit code from your email.")

    otp = (
        EmailSignupOTP.objects.filter(user=user, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not otp:
        raise SignupOTPError("No verification code found. Request a new one.")

    if timezone.now() - otp.created_at > OTP_TTL:
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["consumed_at"])
        raise SignupOTPError("That code has expired. Request a new one.")

    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise SignupOTPError("Too many attempts. Request a new code.")

    otp.attempts += 1
    otp.save(update_fields=["attempts"])

    if not secrets.compare_digest(otp.code_hash, _hash_code(cleaned)):
        remaining = OTP_MAX_ATTEMPTS - otp.attempts
        if remaining <= 0:
            raise SignupOTPError("Too many attempts. Request a new code.")
        raise SignupOTPError(
            f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} left."
        )

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at"])

    if user.approval_status == User.ApprovalStatus.APPROVED:
        user.is_active = True
        user.save(update_fields=["is_active"])

    from allauth.account.models import EmailAddress

    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"verified": True, "primary": True},
    )

    return user


def pending_signup_user(request) -> User | None:
    """Return the signup user stuck in session OTP flow, if any."""
    user_id = request.session.get(SIGNUP_OTP_SESSION_KEY)
    if not user_id:
        return None
    return (
        User.objects.filter(pk=user_id, is_active=False)
        .exclude(approval_status=User.ApprovalStatus.REJECTED)
        .first()
    )


def login_otp_exempt(user) -> bool:
    """Return True when ``user`` may sign in without the emailed login code.

    Superusers are always exempt, plus any address in
    ``settings.LOGIN_OTP_EXEMPT_EMAILS`` (``.env`` only) so no real
    address is hardcoded in the repository.
    """
    if getattr(user, "is_superuser", False):
        return True
    exempt = getattr(settings, "LOGIN_OTP_EXEMPT_EMAILS", ()) or ()
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return False
    return email in {str(item).strip().lower() for item in exempt}


def cleanup_abandoned_signups(
    *,
    older_than: timedelta | None = None,
    limit: int = 200,
    dry_run: bool = False,
) -> dict[str, int]:
    """Delete inactive users who never verified signup OTP past ``older_than``.

    Targets students and faculty who abandoned email verification. Users with a
    verified ``EmailAddress`` (OTP completed) are kept even if still inactive
    (e.g. pending faculty approval). Also drops stale non-primary unverified
    ``EmailAddress`` rows. Returns ``{"users": N, "emails": M}``.
    """
    from allauth.account.models import EmailAddress

    retention = older_than if older_than is not None else ABANDONED_SIGNUP_RETENTION
    cutoff = timezone.now() - retention

    verified_user_ids = set(
        EmailAddress.objects.filter(verified=True).values_list("user_id", flat=True)
    )
    user_ids = list(
        User.objects.filter(is_active=False, date_joined__lt=cutoff)
        .exclude(pk__in=verified_user_ids)
        .exclude(is_superuser=True)
        .order_by("date_joined")
        .values_list("pk", flat=True)[:limit]
    )
    pending_email_count = EmailAddress.objects.filter(
        user_id__in=user_ids, verified=False
    ).count()
    stale_secondary = EmailAddress.objects.filter(
        verified=False,
        primary=False,
        user__date_joined__lt=cutoff,
    )

    if dry_run:
        return {
            "users": len(user_ids),
            "emails": pending_email_count + stale_secondary.count(),
        }

    deleted_users = 0
    if user_ids:
        User.objects.filter(pk__in=user_ids).delete()
        deleted_users = len(user_ids)

    deleted_emails, _ = stale_secondary.delete()
    total_emails = pending_email_count + deleted_emails

    logger.info(
        "cleanup_abandoned_signups: users=%s emails≈%s",
        deleted_users,
        total_emails,
    )
    return {"users": deleted_users, "emails": total_emails}


def maybe_cleanup_abandoned_signups() -> None:
    """Best-effort capped cleanup for local/dev without requiring cron."""
    try:
        cleanup_abandoned_signups(limit=25, dry_run=False)
    except Exception:
        logger.exception("Opportunistic abandoned-signup cleanup failed")

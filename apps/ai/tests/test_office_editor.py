"""ONLYOFFICE Document Server integration for learning materials."""

from __future__ import annotations

import io
import json

import pytest
from django.core.files.base import ContentFile
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.ai.models import LearningDocument
from apps.ai.office_editor import (
    OfficeEditorError,
    absolute_url,
    build_editor_config,
    document_from_token,
    document_key,
    download_edited_document,
    file_token,
    is_editable,
    server_url,
    sign_payload,
    verify_payload,
)


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    """Give every test in this module its own storage root.

    Media is not rolled back with the transaction, so sharing the project
    MEDIA_ROOT leaves suffixed leftovers that make assertions order-dependent.
    Must be active *before* any fixture writes a file.
    """
    settings.MEDIA_ROOT = str(tmp_path / "media")


@pytest.fixture
def office(settings):
    settings.ONLYOFFICE_DOCUMENT_SERVER_URL = "https://office.example.test"
    settings.ONLYOFFICE_JWT_SECRET = "shared-secret"
    settings.ONLYOFFICE_JWT_ENABLED = True
    settings.ONLYOFFICE_EDITABLE_SUFFIXES = (".docx", ".xlsx")
    return settings


@pytest.fixture
def docx_doc(course, subject, professor):
    document = LearningDocument.objects.create(
        course_id=course.pk,
        subject=subject,
        created_by=professor,
        title="Syllabus",
        original_name="syllabus.docx",
        status=LearningDocument.Status.READY,
    )
    document.file.save("syllabus.docx", ContentFile(b"PK\x03\x04docx"), save=True)
    return document


@pytest.fixture
def pdf_doc(course, subject, professor):
    document = LearningDocument.objects.create(
        course_id=course.pk,
        subject=subject,
        created_by=professor,
        title="Scanned",
        original_name="scanned.pdf",
        status=LearningDocument.Status.READY,
    )
    document.file.save("scanned.pdf", ContentFile(b"%PDF-1.4"), save=True)
    return document


class TestConfigurationGating:
    def test_disabled_when_url_unset(self, settings, docx_doc):
        settings.ONLYOFFICE_DOCUMENT_SERVER_URL = ""
        assert is_editable(docx_doc) is False

    @pytest.mark.django_db
    def test_enabled_for_docx_when_configured(self, office, docx_doc):
        assert is_editable(docx_doc) is True

    @pytest.mark.django_db
    def test_pdf_is_never_office_editable(self, office, pdf_doc):
        # PDFs have no paragraph model; reflow editing would need a lossy
        # PDF->DOCX conversion first.
        assert is_editable(pdf_doc) is False

    @pytest.mark.django_db
    def test_trailing_slash_is_normalised(self, settings, docx_doc):
        settings.ONLYOFFICE_DOCUMENT_SERVER_URL = "https://office.example.test/"
        assert server_url() == "https://office.example.test"


class TestJwt:
    def test_round_trip(self, office):
        payload = sign_payload({"status": 2, "key": "abc"})
        assert payload["status"] == 2
        assert payload["token"]
        assert verify_payload(payload)["status"] == 2

    def test_tampered_token_is_rejected(self, office):
        import jwt as pyjwt

        payload = sign_payload({"status": 2})
        # Re-sign with the wrong key: an attacker forging a save command.
        forged = pyjwt.encode({"status": 2}, "wrong-secret", algorithm="HS256")
        payload["token"] = forged
        with pytest.raises(OfficeEditorError):
            verify_payload(payload)

    def test_body_tampering_is_ignored(self, office):
        """Verification returns the signed claims, not the caller's body."""
        payload = sign_payload({"status": 2})
        payload["status"] = 6
        assert verify_payload(payload)["status"] == 2

    def test_missing_token_is_rejected(self, office):
        with pytest.raises(OfficeEditorError):
            verify_payload({"status": 2})

    def test_signing_skipped_when_no_secret(self, settings):
        settings.ONLYOFFICE_JWT_ENABLED = True
        settings.ONLYOFFICE_JWT_SECRET = ""
        payload = sign_payload({"status": 2})
        assert "token" not in payload
        assert verify_payload(payload)["status"] == 2


class TestSignedFileToken:
    @pytest.mark.django_db
    def test_round_trip(self, office, docx_doc):
        token = file_token(docx_doc)
        resolved = document_from_token(token)
        assert resolved is not None and resolved.pk == docx_doc.pk

    @pytest.mark.django_db
    def test_garbage_token_is_rejected(self, office, docx_doc):
        assert document_from_token("not-a-token") is None
        assert document_from_token("") is None

    @pytest.mark.django_db
    def test_token_is_bound_to_the_stored_path(self, office, docx_doc):
        token = file_token(docx_doc)
        # The ONLYOFFICE callback replaces the file in place, so a token issued
        # earlier in the session must keep working.
        docx_doc.file.delete(save=False)
        docx_doc.file.save("syllabus.docx", ContentFile(b"PKnew"), save=True)
        assert document_from_token(token) is not None

        # Moving the file to a different path invalidates it.
        moved = document_from_token(token)
        assert moved is not None
        moved.file.delete(save=False)
        moved.file.save("elsewhere.docx", ContentFile(b"PKnew"), save=True)
        assert document_from_token(token) is None


class TestDocumentKey:
    @pytest.mark.django_db
    def test_key_changes_when_document_changes(self, office, docx_doc):
        first = document_key(docx_doc)
        docx_doc.source_text = "edited"
        docx_doc.save(update_fields=["source_text", "updated"])
        assert document_key(docx_doc) != first


class TestEditorConfig:
    @pytest.mark.django_db
    def test_config_carries_jwt_and_callback(self, office, docx_doc, professor):
        config = build_editor_config(
            docx_doc,
            user=professor,
            file_url="https://app.example.test/file/?token=x",
            callback_url="https://app.example.test/callback/",
        )
        assert config["document"]["fileType"] == "docx"
        assert config["document"]["key"]
        assert config["editorConfig"]["callbackUrl"].endswith("/callback/")
        assert config["token"]

    def test_raises_when_unconfigured(self, settings, docx_doc):
        settings.ONLYOFFICE_DOCUMENT_SERVER_URL = ""
        with pytest.raises(OfficeEditorError):
            build_editor_config(
                docx_doc,
                user=None,
                file_url="u",
                callback_url="c",
            )


@pytest.mark.django_db
class TestPublicBaseUrl:
    """The Document Server must not be handed a private origin."""

    def test_falls_back_to_request_host(self, settings):
        settings.ONLYOFFICE_PUBLIC_BASE_URL = ""
        request = RequestFactory().get("/x/")
        assert absolute_url(request, "/x/") == "http://testserver/x/"

    def test_public_override_wins(self, settings):
        settings.ONLYOFFICE_PUBLIC_BASE_URL = "https://tunnel.example.dev"
        request = RequestFactory().get("/x/")
        assert absolute_url(request, "/x/") == "https://tunnel.example.dev/x/"

    def test_trailing_slash_is_trimmed(self, settings):
        settings.ONLYOFFICE_PUBLIC_BASE_URL = "https://tunnel.example.dev/"
        request = RequestFactory().get("/x/")
        assert absolute_url(request, "/x/") == "https://tunnel.example.dev/x/"


class TestDownloadGuards:
    @pytest.mark.django_db
    def test_rejects_foreign_host(self, office, docx_doc):
        with pytest.raises(OfficeEditorError):
            download_edited_document(docx_doc, "http://169.254.169.254/latest/meta-data/")

    @pytest.mark.django_db
    def test_rejects_empty_url(self, office, docx_doc):
        with pytest.raises(OfficeEditorError):
            download_edited_document(docx_doc, "")

    @pytest.mark.django_db
    def test_downloads_from_the_server_host(self, office, docx_doc, monkeypatch):
        captured = {}

        class _Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=65536):
                captured["url"] = True
                yield b"PK\x03\x04edited"

        import requests

        def _get(url, timeout=None, stream=None):
            captured["requested"] = url
            return _Response()

        monkeypatch.setattr(requests, "get", _get)
        data = download_edited_document(
            docx_doc, "https://office.example.test/cache/files/out.docx"
        )
        assert data == b"PK\x03\x04edited"
        assert captured["requested"].startswith("https://office.example.test")


@pytest.mark.django_db
class TestConfigEndpoint:
    def _url(self, course, document):
        return reverse(
            "analytics_professor:material_office_config",
            kwargs={"course_pk": course.pk, "pk": document.pk},
        )

    def test_returns_disabled_when_not_configured(
        self, client, professor, course, settings, docx_doc
    ):
        settings.ONLYOFFICE_DOCUMENT_SERVER_URL = ""
        client.force_login(professor)
        response = client.post(self._url(course, docx_doc))
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_returns_config_when_configured(
        self, client, professor, course, office, docx_doc
    ):
        client.force_login(professor)
        response = client.post(self._url(course, docx_doc))
        data = response.json()
        assert data["enabled"] is True
        assert data["api_url"].endswith("/api.js")
        assert data["config"]["token"]
        assert "token=" in data["config"]["document"]["url"]

    def test_pdf_gets_disabled_response(
        self, client, professor, course, office, pdf_doc
    ):
        client.force_login(professor)
        response = client.post(self._url(course, pdf_doc))
        assert response.json()["enabled"] is False

    def test_requires_authentication(self, client, course, office, docx_doc):
        response = client.post(self._url(course, docx_doc))
        assert response.status_code in (302, 403, 404)


@pytest.mark.django_db
class TestSignedFileEndpoint:
    def _url(self, course, document):
        return reverse(
            "analytics_professor:material_office_file",
            kwargs={"course_pk": course.pk, "pk": document.pk},
        )

    def test_valid_token_serves_the_file(
        self, client, course, office, docx_doc
    ):
        url = f"{self._url(course, docx_doc)}?token={file_token(docx_doc)}"
        response = client.get(url)
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"PK\x03\x04docx"

    def test_missing_token_is_404(self, client, course, office, docx_doc):
        assert client.get(self._url(course, docx_doc)).status_code == 404

    def test_token_from_another_document_is_404(
        self, client, professor, course, subject, office, docx_doc
    ):
        other = LearningDocument.objects.create(
            course_id=course.pk,
            subject=subject,
            created_by=professor,
            title="Other",
            original_name="other.docx",
            status=LearningDocument.Status.READY,
        )
        other.file.save("other.docx", ContentFile(b"PKother"), save=True)
        url = f"{self._url(course, other)}?token={file_token(docx_doc)}"
        assert client.get(url).status_code == 404


@pytest.mark.django_db
class TestCallbackEndpoint:
    def _url(self, course, document):
        return reverse(
            "analytics_professor:material_office_callback",
            kwargs={"course_pk": course.pk, "pk": document.pk},
        )

    def _payload(self, status, url=None, **extra):
        body = {"status": status, "key": "k", **extra}
        if url:
            body["url"] = url
        return json.dumps(sign_payload(body))

    def test_callback_is_exempt_from_csrf(
        self, course, office, docx_doc, monkeypatch
    ):
        """The Document Server posts without a CSRF token, so it must not 403.

        Uses a CSRF-enforcing client: the default test client skips CSRF checks,
        which would hide a missing ``csrf_exempt``.
        """
        import requests

        class _Response:
            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=65536):
                yield b"PK\x03\x04NEWCONTENT"

        monkeypatch.setattr(
            requests, "get", lambda url, timeout=None, stream=None: _Response()
        )
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(docx_doc.created_by)
        # No CSRF token supplied: the middleware would reject this with 403.
        response = strict.post(
            self._url(course, docx_doc),
            data=self._payload(2, url="https://office.example.test/out.docx"),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_saves_edited_file_on_status_2(
        self, client, course, office, docx_doc, monkeypatch
    ):
        import requests

        class _Response:
            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=65536):
                yield b"PK\x03\x04NEWCONTENT"

        monkeypatch.setattr(
            requests, "get", lambda url, timeout=None, stream=None: _Response()
        )

        response = client.post(
            self._url(course, docx_doc),
            self._payload(
                2, "https://office.example.test/cache/files/new.docx"
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {"error": 0}

        docx_doc.refresh_from_db()
        docx_doc.file.open("rb")
        try:
            assert docx_doc.file.read() == b"PK\x03\x04NEWCONTENT"
        finally:
            docx_doc.file.close()

    def test_ignores_editing_status(self, client, course, office, docx_doc):
        response = client.post(
            self._url(course, docx_doc),
            self._payload(1),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {"error": 0}

    def test_rejects_unsigned_callback(self, client, course, office, docx_doc):
        response = client.post(
            self._url(course, docx_doc),
            json.dumps({"status": 2, "url": "https://office.example.test/x.docx"}),
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_rejects_foreign_download_host(
        self, client, course, office, docx_doc
    ):
        response = client.post(
            self._url(course, docx_doc),
            self._payload(2, "http://169.254.169.254/latest/meta-data/"),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_malformed_json_is_400(self, client, course, office, docx_doc):
        response = client.post(
            self._url(course, docx_doc),
            "not json",
            content_type="application/json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestDetailPageIntegration:
    def test_office_editor_is_mounted_when_enabled(
        self, client, professor, course, office, docx_doc
    ):
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:material_detail",
                kwargs={"course_pk": course.pk, "pk": docx_doc.pk},
            )
        )
        content = response.content.decode()
        assert "data-office-root" in content
        assert "materials-office.js" in content
        # The built-in editor stays in the DOM as the fallback.
        assert "data-editor-form" in content

    def test_builtin_editor_used_when_disabled(
        self, client, professor, course, settings, docx_doc
    ):
        settings.ONLYOFFICE_DOCUMENT_SERVER_URL = ""
        client.force_login(professor)
        content = client.get(
            reverse(
                "analytics_professor:material_detail",
                kwargs={"course_pk": course.pk, "pk": docx_doc.pk},
            )
        ).content.decode()
        assert "data-office-root" not in content
        assert "materials-editor.js" in content

    def test_pdf_offers_no_editor_at_all(
        self, client, professor, course, office, pdf_doc
    ):
        """PDFs are view/download only: neither editor may mount."""
        client.force_login(professor)
        content = client.get(
            reverse(
                "analytics_professor:material_detail",
                kwargs={"course_pk": course.pk, "pk": pdf_doc.pk},
            )
        ).content.decode()
        assert "data-office-root" not in content
        assert "data-editor-form" not in content
        assert "materials-office.js" not in content
        assert "materials-editor.js" not in content
        # Read-only notice plus a way to get the file.
        assert "be edited here yet" in content
        assert "/download/" in content


def test_docx_round_trip_payload_is_a_valid_zip():
    """Sanity check that our exported DOCX is a real Office container."""
    import docx as docx_lib

    from apps.ai.document_html import html_to_docx_bytes

    payload = html_to_docx_bytes(
        "<h1>Heading</h1><p>Body <strong>bold</strong>.</p><ul><li>One</li></ul>"
    )
    assert payload[:2] == b"PK"
    document = docx_lib.Document(io.BytesIO(payload))
    styles = {p.style.name for p in document.paragraphs}
    assert "Heading 1" in styles
    assert "List Bullet" in styles
"""Unit tests for Resend HTTPS OTP delivery."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail

from apps.users.otp_services import (
    SignupOTPError,
    _deliver_otp_email,
    _should_use_resend_api,
    send_signup_otp,
)


@pytest.mark.django_db
class TestResendApiDelivery:
    def test_uses_django_backend_when_locmem(self, settings, professor):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.RESEND_API_KEY = "re_test_key"
        assert _should_use_resend_api() is False

        send_signup_otp(professor, force=True)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].alternatives

    def test_resend_api_posts_json_payload(self, settings, professor):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.RESEND_API_KEY = "re_test_key"
        settings.DEFAULT_FROM_EMAIL = "ExamiQ <onboarding@examiq.xyz>"
        settings.EMAIL_TIMEOUT = 5
        assert _should_use_resend_api() is True

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_response.read.return_value = b'{"id":"msg_1"}'

        with patch(
            "apps.users.otp_services.urllib.request.urlopen",
            return_value=mock_response,
        ) as urlopen:
            send_signup_otp(professor, force=True)

        assert urlopen.called
        request = urlopen.call_args.args[0]
        assert request.full_url == "https://api.resend.com/emails"
        assert request.get_header("Authorization") == "Bearer re_test_key"
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["to"] == [professor.email]
        assert payload["from"] == "ExamiQ <onboarding@examiq.xyz>"
        assert "verification code" in payload["subject"].lower()
        assert "html" in payload and "text" in payload
        assert len(mail.outbox) == 0

    def test_resend_http_error_raises_signup_otp_error(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.RESEND_API_KEY = "re_test_key"

        error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            url="https://api.resend.com/emails",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"message":"API key is invalid"}'),
        )
        with (
            patch(
                "apps.users.otp_services.urllib.request.urlopen",
                side_effect=error,
            ),
            pytest.raises(SignupOTPError, match="Resend API"),
        ):
            _deliver_otp_email(
                subject="Test",
                text_body="text",
                html_body="<p>html</p>",
                to_email="user@example.com",
            )

    def test_password_re_prefix_enables_api(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.RESEND_API_KEY = ""
        settings.EMAIL_HOST_PASSWORD = "re_from_password"
        assert _should_use_resend_api() is True

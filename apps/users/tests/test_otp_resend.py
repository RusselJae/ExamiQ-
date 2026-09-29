"""Unit tests for Resend HTTPS OTP delivery."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from resend.exceptions import ResendError

from apps.users.otp_services import (
    SignupOTPError,
    _deliver_otp_email,
    _send_via_resend_urllib,
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

    def test_resend_sdk_sends_payload(self, settings, professor):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.RESEND_API_KEY = "re_test_key"
        settings.DEFAULT_FROM_EMAIL = "ExamiQ <onboarding@examiq.xyz>"
        assert _should_use_resend_api() is True

        with patch(
            "resend.Emails.send",
            return_value={"id": "msg_1"},
        ) as send_mock:
            send_signup_otp(professor, force=True)

        assert send_mock.called
        payload = send_mock.call_args.args[0]
        assert payload["to"] == [professor.email]
        assert payload["from"] == "ExamiQ <onboarding@examiq.xyz>"
        assert "verification code" in payload["subject"].lower()
        assert "html" in payload and "text" in payload
        assert len(mail.outbox) == 0

    def test_resend_sdk_error_raises_signup_otp_error(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.RESEND_API_KEY = "re_test_key"

        with (
            patch(
                "resend.Emails.send",
                side_effect=ResendError(
                    401,
                    "invalid_api_key",
                    "API key is invalid",
                    "",
                ),
            ),
            pytest.raises(SignupOTPError, match="Resend API"),
        ):
            _deliver_otp_email(
                subject="Test",
                text_body="text",
                html_body="<p>html</p>",
                to_email="user@example.com",
            )

    def test_urllib_fallback_sets_user_agent(self, settings):
        settings.EMAIL_TIMEOUT = 5
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_response.read.return_value = b'{"id":"msg_1"}'

        with patch(
            "apps.users.otp_services.urllib.request.urlopen",
            return_value=mock_response,
        ) as urlopen:
            _send_via_resend_urllib(
                api_key="re_test_key",
                payload={
                    "from": "ExamiQ <onboarding@examiq.xyz>",
                    "to": ["user@example.com"],
                    "subject": "Test",
                    "text": "text",
                    "html": "<p>html</p>",
                },
            )

        request = urlopen.call_args.args[0]
        assert "ExamiQ/1.0" in request.get_header("User-agent")
        assert request.get_header("Authorization") == "Bearer re_test_key"
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["to"] == ["user@example.com"]

    def test_urllib_http_error_raises(self, settings):
        error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            url="https://api.resend.com/emails",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(b'{"message":"Access denied"}'),
        )
        with (
            patch(
                "apps.users.otp_services.urllib.request.urlopen",
                side_effect=error,
            ),
            pytest.raises(SignupOTPError, match="Resend API"),
        ):
            _send_via_resend_urllib(
                api_key="re_test_key",
                payload={
                    "from": "a@b.com",
                    "to": ["c@d.com"],
                    "subject": "s",
                    "text": "t",
                    "html": "h",
                },
            )

    def test_password_re_prefix_enables_api(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.RESEND_API_KEY = ""
        settings.EMAIL_HOST_PASSWORD = "re_from_password"
        assert _should_use_resend_api() is True

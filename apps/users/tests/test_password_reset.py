"""Password reset pages and Resend delivery via ExamiQAccountAdapter."""

from unittest.mock import MagicMock, patch

import pytest
from allauth.core.context import request_context
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse

from apps.users.adapters import ExamiQAccountAdapter
from apps.users.otp_services import SignupOTPError


@pytest.mark.django_db
class TestPasswordResetPages:
    @pytest.fixture(autouse=True)
    def _locmem_email(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    def test_reset_page_uses_auth_chrome(self, client):
        response = client.get(reverse("account_reset_password"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "auth-page__heading" in content
        assert "Forgot password" in content
        assert "auth-btn-submit" in content

    def test_reset_done_page_uses_auth_chrome(self, client):
        response = client.get(reverse("account_reset_password_done"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "auth-page__heading" in content
        assert "Check your email" in content

    def test_reset_post_queues_email(self, client, student):
        response = client.post(
            reverse("account_reset_password"),
            {"email": student.email},
        )
        assert response.status_code == 302
        assert reverse("account_reset_password_done") in response.url
        assert len(mail.outbox) == 1
        assert "reset" in mail.outbox[0].subject.lower()
        body = mail.outbox[0].body
        assert "password" in body.lower()
        assert mail.outbox[0].alternatives
        html = mail.outbox[0].alternatives[0][0]
        assert "ExamiQ" in html
        assert "Reset password" in html


@pytest.mark.django_db
class TestPasswordResetResendAdapter:
    def test_send_mail_uses_resend_when_configured(self, settings, rf):
        settings.RESEND_API_KEY = "re_test_key"
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.DEFAULT_FROM_EMAIL = "ExamiQ <noreply@example.com>"

        request = rf.get("/")
        adapter = ExamiQAccountAdapter()
        real_msg = EmailMultiAlternatives(
            subject="Reset your ExamiQ password",
            body="text body",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=["ada@test.edu"],
        )
        real_msg.attach_alternative("<p>HTML Reset</p>", "text/html")

        with (
            request_context(request),
            patch.object(adapter, "render_mail", return_value=real_msg),
            patch("apps.users.adapters._send_via_resend_api") as mock_resend,
        ):
            adapter.send_mail(
                "account/email/password_reset_key",
                "ada@test.edu",
                {
                    "user": MagicMock(),
                    "password_reset_url": "https://example.com/reset/abc",
                },
            )

            mock_resend.assert_called_once()
            kwargs = mock_resend.call_args.kwargs
            assert kwargs["to_email"] == "ada@test.edu"
            assert "reset" in kwargs["subject"].lower()
            assert "HTML Reset" in kwargs["html_body"]

    def test_send_mail_falls_back_when_resend_fails(self, settings, rf):
        settings.RESEND_API_KEY = "re_test_key"
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.DEFAULT_FROM_EMAIL = "ExamiQ <noreply@example.com>"

        request = rf.get("/")
        adapter = ExamiQAccountAdapter()
        real_msg = EmailMultiAlternatives(
            subject="Reset",
            body="text",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=["ada@test.edu"],
        )
        real_msg.attach_alternative("<p>HTML</p>", "text/html")

        with (
            request_context(request),
            patch.object(adapter, "render_mail", return_value=real_msg),
            patch(
                "apps.users.adapters._send_via_resend_api",
                side_effect=SignupOTPError("fail"),
            ),
            patch.object(real_msg, "send") as mock_send,
        ):
            adapter.send_mail(
                "account/email/password_reset_key",
                "ada@test.edu",
                {"password_reset_url": "https://example.com/x", "user": MagicMock()},
            )
            mock_send.assert_called_once()

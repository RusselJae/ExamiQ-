"""Regression tests: login-by-code loop escape and login OTP exemption."""

import pytest
from django.urls import reverse

from apps.users.models import User
from apps.users.otp_services import login_otp_exempt


@pytest.mark.django_db
def _start_login_code_stage(client, user, password="testpass123"):
    """Log in far enough that a login-by-code stage is pending."""
    response = client.post(
        reverse("account_login"), {"login": user.email, "password": password}
    )
    assert response.status_code == 302
    assert response.url == "/accounts/login/code/confirm/"
    return response


@pytest.mark.django_db
class TestLoginCodeLoop:
    def test_login_page_renders_while_code_pending(self, client, professor):
        _start_login_code_stage(client, professor)
        page = client.get(reverse("account_login"))
        assert page.status_code == 200
        assert b"Sign in" in page.content

    def test_signup_page_renders_while_code_pending(self, client, professor):
        _start_login_code_stage(client, professor)
        page = client.get(reverse("account_signup"))
        assert page.status_code == 200

    def test_login_page_works_again_after_back_navigation(self, client, professor):
        _start_login_code_stage(client, professor)
        client.get(reverse("account_login"))
        # Signing in with different credentials must not bounce to the code screen.
        second = User.objects.create_user(
            email="other-prof@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=professor.department,
        )
        response = client.post(
            reverse("account_login"),
            {"login": second.email, "password": "testpass123"},
        )
        assert response.url == "/accounts/login/code/confirm/"

    def test_code_screen_offers_resend_and_exit(self, client, professor):
        _start_login_code_stage(client, professor)
        page = client.get("/accounts/login/code/confirm/")
        assert page.status_code == 200
        assert b"Resend code" in page.content
        assert b"Back to sign in" in page.content

    def test_empty_code_does_not_redirect(self, client, professor):
        _start_login_code_stage(client, professor)
        response = client.post("/accounts/login/code/confirm/", {"code": ""})
        assert response.status_code == 200


@pytest.mark.django_db
class TestLoginOTPExemption:
    def test_exempt_professor_skips_code_stage(self, client, settings, professor):
        settings.LOGIN_OTP_EXEMPT_EMAILS = {professor.email}
        response = client.post(
            reverse("account_login"),
            {"login": professor.email, "password": "testpass123"},
        )
        assert response.url != "/accounts/login/code/confirm/"
        assert "_auth_user_id" in client.session

    def test_other_professor_still_requires_code(self, client, settings, professor):
        settings.LOGIN_OTP_EXEMPT_EMAILS = {"someone.else@examiq.edu"}
        _start_login_code_stage(client, professor)
        assert "_auth_user_id" not in client.session

    def test_exemption_is_case_insensitive(self, professor, settings):
        settings.LOGIN_OTP_EXEMPT_EMAILS = {"PROF_EducMath@ExamiQ.EDU"}
        assert login_otp_exempt(professor) is False
        professor.email = "prof_educmath@examiq.edu"
        assert login_otp_exempt(professor) is True

    def test_no_exempt_configured_by_default(self, professor, settings):
        settings.LOGIN_OTP_EXEMPT_EMAILS = set()
        assert login_otp_exempt(professor) is False


@pytest.mark.django_db
class TestSignupOTPExit:
    def test_cancel_clears_session_and_redirects_to_login(self, client, professor):
        professor.is_active = False
        professor.approval_status = User.ApprovalStatus.APPROVED
        professor.save(update_fields=["is_active", "approval_status"])
        client.post(
            reverse("account_login"),
            {"login": professor.email, "password": "testpass123"},
        )
        assert client.session.get("signup_otp_user_id") == professor.pk

        response = client.post(reverse("users:signup_verify"), {"action": "cancel"})
        assert response.status_code == 302
        assert response.url == reverse("account_login")
        assert client.session.get("signup_otp_user_id") is None

        # The login page is reachable again instead of bouncing to the code screen.
        assert client.get(reverse("account_login")).status_code == 200

    def test_verify_page_offers_cancel(self, client, professor):
        professor.is_active = False
        professor.save(update_fields=["is_active"])
        session = client.session
        session["signup_otp_user_id"] = professor.pk
        session.save()

        page = client.get(reverse("users:signup_verify"))
        assert page.status_code == 200
        assert b"Cancel and go to sign in" in page.content

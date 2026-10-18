"""Unlisted coordinator signup tests (secret link) + shared sign-in."""

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.users.models import User

TOKEN = "test-coordinator-token-123"


@pytest.fixture(autouse=True)
def _portal_token(settings):
    settings.COORDINATOR_PORTAL_TOKEN = TOKEN
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    cache.clear()
    yield
    cache.clear()


def _coordinator_data(department, **extra):
    data = {
        "role": User.Role.PROGRAM_COORDINATOR,
        "email": "newcoord@test.edu",
        "password1": "strongpass123!",
        "password2": "strongpass123!",
        "first_name": "Ada",
        "last_name": "Reyes",
        "middle_name": "",
        "suffix": "",
        "employee_id": "COORD-001",
        "phone_number": "09123456789",
        "department": department.pk,
    }
    data.update(extra)
    return data


@pytest.mark.django_db
class TestCoordinatorPortal:
    def test_wrong_token_returns_404(self, client):
        assert (
            client.get(
                reverse("account_coordinator_signup", args=["wrong"])
            ).status_code
            == 404
        )

    def test_signup_not_linked_from_public_pages(self, client):
        signup_html = client.get(reverse("account_signup")).content.decode()
        assert "accounts/coordinator" not in signup_html
        assert (
            "accounts/coordinator"
            not in client.get(reverse("account_login")).content.decode()
        )

    def test_signup_creates_pending_coordinator(self, client, department):
        from django.core import mail

        from apps.users.otp_services import SIGNUP_OTP_SESSION_KEY

        response = client.post(
            reverse("account_coordinator_signup", args=[TOKEN]),
            _coordinator_data(department),
        )
        assert response.status_code == 302
        user = User.objects.get(email="newcoord@test.edu")
        assert user.role == User.Role.PROGRAM_COORDINATOR
        assert user.department_id == department.pk
        assert user.approval_status == User.ApprovalStatus.PENDING
        assert user.is_active is False
        assert client.session.get(SIGNUP_OTP_SESSION_KEY) == user.pk
        assert len(mail.outbox) == 1

    def test_otp_verify_keeps_coordinator_pending(self, client, department):
        from django.core import mail

        client.post(
            reverse("account_coordinator_signup", args=[TOKEN]),
            _coordinator_data(department),
        )
        body = mail.outbox[-1].body
        code = next(t for t in body.split() if t.isdigit() and len(t) == 6)
        response = client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": code},
        )
        assert response.status_code == 302
        user = User.objects.get(email="newcoord@test.edu")
        assert user.approval_status == User.ApprovalStatus.PENDING
        assert user.is_active is False

    def test_shared_signin_accepts_faculty_and_coordinator(
        self, client, department, settings
    ):
        """Faculty and coordinators use the same public sign-in page."""
        for email, role in (
            ("prof-shared@test.edu", User.Role.PROFESSOR),
            ("coord-shared@test.edu", User.Role.PROGRAM_COORDINATOR),
        ):
            User.objects.create_user(
                email=email,
                password="strongpass123!",
                role=role,
                department=department,
                approval_status=User.ApprovalStatus.APPROVED,
                is_active=True,
            )
        settings.LOGIN_OTP_EXEMPT_EMAILS = {
            "prof-shared@test.edu",
            "coord-shared@test.edu",
        }
        for email in ("prof-shared@test.edu", "coord-shared@test.edu"):
            client.logout()
            response = client.post(
                reverse("account_login"),
                {"login": email, "password": "strongpass123!"},
            )
            assert response.status_code == 302
            assert "_auth_user_id" in client.session

    def test_faculty_signup_is_unlisted(self, client, settings):
        """Faculty signup lives behind its own secret token, linked nowhere."""
        settings.FACULTY_PORTAL_TOKEN = "faculty-secret-789"
        signup_html = client.get(reverse("account_signup")).content.decode()
        assert "Request a faculty account" not in signup_html
        assert "faculty/" not in signup_html
        assert (
            client.get(reverse("account_faculty_signup", args=["wrong"])).status_code
            == 404
        )
        assert (
            client.get(
                reverse("account_faculty_signup", args=["faculty-secret-789"])
            ).status_code
            == 200
        )

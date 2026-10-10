"""Auth hardening: password-reset limits, name validation, login OTP gate."""

import pytest
from django.core import mail
from django.urls import reverse

from apps.users.name_validation import clean_person_name
from apps.users.password_reset_services import (
    PasswordResetThrottleError,
    check_password_reset_allowed,
    record_password_reset_request,
)


@pytest.mark.django_db
class TestNameValidation:
    def test_accepts_letters_spaces_hyphens_apostrophes(self):
        assert clean_person_name("Mary-Jane O'Neil") == "Mary-Jane O'Neil"

    def test_rejects_digits(self):
        with pytest.raises(Exception):
            clean_person_name("John2")

    def test_rejects_over_100(self):
        with pytest.raises(Exception):
            clean_person_name("A" * 101)


@pytest.mark.django_db
class TestPasswordResetLimits:
    @pytest.fixture(autouse=True)
    def _email(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.PASSWORD_RESET_COOLDOWN_SECONDS = 30
        settings.PASSWORD_RESET_DAILY_LIMIT = 3

    def test_unknown_email_rejected(self, client):
        response = client.post(
            reverse("account_reset_password"),
            {"email": "nobody@example.com"},
        )
        assert response.status_code == 200
        assert b"No account is registered" in response.content
        assert len(mail.outbox) == 0

    def test_known_email_sends(self, client, student):
        response = client.post(
            reverse("account_reset_password"),
            {"email": student.email},
        )
        assert response.status_code == 302
        assert len(mail.outbox) == 1

    def test_daily_limit_returns_429(self, client, student):
        for _ in range(3):
            record_password_reset_request(student.email)
        response = client.post(
            reverse("account_reset_password"),
            {"email": student.email},
        )
        assert response.status_code == 429
        assert b"Too many requests" in response.content
        assert b"account_login" in response.content or b"sign in" in response.content.lower()

    def test_cooldown_blocks_immediate_retry(self, student):
        record_password_reset_request(student.email)
        with pytest.raises(PasswordResetThrottleError):
            check_password_reset_allowed(student.email)


@pytest.mark.django_db
class TestFacultyLoginRequiresCodeStage:
    def test_adapter_requires_code_for_professor(self, professor, rf):
        from allauth.account.models import Login

        from apps.users.adapters import ExamiQAccountAdapter

        request = rf.get("/")
        adapter = ExamiQAccountAdapter()
        adapter.request = request
        login = Login(user=professor, email=professor.email)
        assert adapter.is_login_by_code_required(login) is True

    def test_adapter_skips_code_for_student(self, student, rf):
        from allauth.account.models import Login

        from apps.users.adapters import ExamiQAccountAdapter

        request = rf.get("/")
        adapter = ExamiQAccountAdapter()
        adapter.request = request
        login = Login(user=student, email=student.email)
        assert adapter.is_login_by_code_required(login) is False

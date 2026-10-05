"""Faculty signup PIN profile management and verification."""

import pytest
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.urls import reverse

from apps.users.faculty_pin_services import (
    faculty_signup_pin_is_configured,
    update_faculty_signup_pin,
    verify_faculty_signup_pin,
)
from apps.users.models import FacultySignupPinSettings


@pytest.mark.django_db
class TestFacultySignupPinServices:
    def test_env_pin_is_used_when_db_empty(self, settings):
        settings.FACULTY_SIGNUP_PIN = "ENV-PIN-123"
        assert faculty_signup_pin_is_configured() is True
        assert verify_faculty_signup_pin("ENV-PIN-123") is True
        assert verify_faculty_signup_pin("wrong") is False

    def test_db_pin_overrides_env(self, settings):
        settings.FACULTY_SIGNUP_PIN = "ENV-PIN-123"
        pin_settings = FacultySignupPinSettings.load()
        pin_settings.pin_hash = make_password("DB-PIN-456")
        pin_settings.save(update_fields=["pin_hash"])
        assert verify_faculty_signup_pin("DB-PIN-456") is True
        assert verify_faculty_signup_pin("ENV-PIN-123") is False


@pytest.mark.django_db
class TestFacultySignupPinProfile:
    @pytest.fixture(autouse=True)
    def _locmem_email(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    def test_professor_profile_shows_faculty_pin_section(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("users:profile"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "Faculty signup PIN" in content
        assert "update_faculty_pin" in content

    def test_chairperson_profile_shows_faculty_pin_section(self, client, chairperson):
        client.force_login(chairperson)
        response = client.get(reverse("users:profile"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "Faculty signup PIN" in content

    def test_student_profile_hides_faculty_pin_section(self, client, student):
        client.force_login(student)
        response = client.get(reverse("users:profile"))
        content = response.content.decode()
        assert "Faculty signup PIN" not in content

    def test_professor_can_update_pin_and_notify_other_faculty(
        self, client, professor, chairperson
    ):
        client.force_login(professor)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_faculty_pin",
                "new_pin": "FACULTY-NEW-99",
                "confirm_pin": "FACULTY-NEW-99",
                "password": "testpass123",
            },
        )
        assert response.status_code == 302
        assert verify_faculty_signup_pin("FACULTY-NEW-99") is True
        pin_settings = FacultySignupPinSettings.load()
        assert pin_settings.updated_by_id == professor.pk
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [chairperson.email]
        assert "FACULTY-NEW-99" in mail.outbox[0].body
        assert professor.get_full_name() in mail.outbox[0].body or professor.email in mail.outbox[0].body

    def test_pin_change_requires_account_password(self, client, professor, chairperson):
        client.force_login(professor)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_faculty_pin",
                "new_pin": "FACULTY-NEW-99",
                "confirm_pin": "FACULTY-NEW-99",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 200
        assert b"Incorrect account password" in response.content
        assert len(mail.outbox) == 0

    def test_pin_change_rejects_mismatched_confirmation(self, client, professor):
        client.force_login(professor)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_faculty_pin",
                "new_pin": "FACULTY-NEW-99",
                "confirm_pin": "FACULTY-OTHER-99",
                "password": "testpass123",
            },
        )
        assert response.status_code == 200
        assert b"PINs do not match" in response.content

    def test_service_update_notifies_other_faculty_only(
        self, professor, chairperson, settings
    ):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        update_faculty_signup_pin(changed_by=professor, new_pin="SERVICE-PIN-77")
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [chairperson.email]
        assert "SERVICE-PIN-77" in mail.outbox[0].body

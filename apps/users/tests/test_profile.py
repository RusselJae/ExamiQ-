import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from allauth.account.models import EmailAddress

from conftest import make_bsed_student

User = get_user_model()


def _student_profile_fields(student, **overrides):
    """Required student profile fields for ProfileUpdateForm POSTs."""
    fields = {}
    if student.year_level_id:
        fields["year_level"] = student.year_level_id
    if student.section_id:
        fields["section"] = student.section.label
    fields.update(overrides)
    return fields


@pytest.mark.django_db
class TestProfileView:
    def test_profile_requires_login(self, client):
        response = client.get(reverse("users:profile"))
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_profile_page_renders_for_student(self, client, student):
        student.first_name = "Alex"
        student.last_name = "Student"
        student.save()
        client.force_login(student)
        response = client.get(reverse("users:profile"))
        assert response.status_code == 200
        content = response.content.decode()
        assert student.email in content
        assert "Student" in content
        assert "Login email" in content
        assert "profile-bento" in content
        assert "profile-avatar-wrap--hero" in content
        assert "profile-avatar-wrap--form" not in content
        assert "profile-avatar-camera" in content
        assert "profile-update-form" in content
        assert "Pilot Study" not in content
        assert "id_year_level" in content
        assert "id_section" in content

    def test_student_can_save_section(
        self, client, student, bsed_program, year_level, program_section, academic_year
    ):
        from apps.users.models import ProgramSection

        ProgramSection.objects.filter(pk=program_section.pk).update(program=bsed_program)
        program_section.refresh_from_db()
        make_bsed_student(student, bsed_program=bsed_program)
        student.year_level = year_level
        student.section = program_section
        student.save(update_fields=["year_level", "section"])

        other_section, _ = ProgramSection.objects.get_or_create(
            program=bsed_program,
            year_level=year_level,
            label="2M",
            academic_year=academic_year,
            defaults={"max_students": 40, "is_active": True},
        )

        client.force_login(student)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": student.first_name,
                "last_name": student.last_name,
                "year_level": year_level.pk,
                "section": other_section.label,
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.section_id == other_section.pk

    def test_student_profile_uses_bento_layout(self, client, student):
        client.force_login(student)
        response = client.get(reverse("users:profile"))
        content = response.content.decode()
        assert "profile-page--student" not in content
        assert "profile-bento" in content

    def test_professor_profile_uses_bento_layout(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("users:profile"))
        content = response.content.decode()
        assert "profile-page--student" not in content
        assert "profile-bento" in content

    def test_professor_profile_shows_assignment_fields(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("users:profile"))
        content = response.content.decode()
        assert "Teaching assignments" in content
        assert "profile-bento--faculty" in content
        assert "assigned_sections" in content
        assert "assigned_subjects" in content
        assert "data-multi-select" in content
        assert "multi-select-dropdown.js" in content

    def test_professor_can_save_sections_and_subjects(
        self, client, professor, program_section, subject, bsed_program
    ):
        from apps.questions.models import Subject
        from apps.users.models import ProgramSection

        Subject.objects.filter(pk=subject.pk).update(program=bsed_program)
        ProgramSection.objects.filter(pk=program_section.pk).update(program=bsed_program)
        subject.refresh_from_db()
        program_section.refresh_from_db()

        client.force_login(professor)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": "Fac",
                "last_name": "Ulty",
                "assigned_sections": [program_section.pk],
                "assigned_subjects": [subject.pk],
            },
        )
        assert response.status_code == 302
        professor.refresh_from_db()
        assert list(professor.assigned_sections.values_list("pk", flat=True)) == [
            program_section.pk
        ]
        assert list(professor.assigned_subjects.values_list("pk", flat=True)) == [
            subject.pk
        ]

    def test_update_name(self, client, student):
        client.force_login(student)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": "Updated",
                "last_name": "Name",
                **_student_profile_fields(student),
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.first_name == "Updated"
        assert student.last_name == "Name"

    def test_update_middle_name(self, client, student):
        client.force_login(student)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": "Alex",
                "middle_name": "Q",
                "last_name": "Student",
                **_student_profile_fields(student),
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.middle_name == "Q"
        assert student.get_full_name() == "Alex Q Student"

    def test_update_suffix(self, client, student):
        client.force_login(student)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": "Alex",
                "middle_name": "",
                "last_name": "Student",
                "suffix": "Jr.",
                **_student_profile_fields(student),
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.suffix == "Jr."
        assert student.get_full_name() == "Alex Student Jr."

    def test_upload_profile_photo(self, client, student):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
        client.force_login(student)
        photo = SimpleUploadedFile("avatar.png", buf.getvalue(), content_type="image/png")
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": "Alex",
                "middle_name": "",
                "last_name": "Student",
                "profile_photo": photo,
                **_student_profile_fields(student),
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.profile_photo

    def test_change_password(self, client, student):
        client.force_login(student)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "change_password",
                "oldpassword": "testpass123",
                "password1": "newpass456!",
                "password2": "newpass456!",
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.check_password("newpass456!")

    def test_email_change_sends_confirmation(self, client, student):
        client.force_login(student)
        new_email = "newaddr@test.edu"
        response = client.post(
            reverse("users:profile"),
            {
                "action": "request_email_change",
                "email": new_email,
            },
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.email == "student@test.edu"

        pending = EmailAddress.objects.filter(user=student, verified=False)
        assert pending.count() == 1
        assert pending.first().email == new_email
        assert len(mail.outbox) == 1
        assert new_email in mail.outbox[0].to

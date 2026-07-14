import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from allauth.account.models import EmailAddress

User = get_user_model()


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

    def test_update_name(self, client, student):
        client.force_login(student)
        response = client.post(
            reverse("users:profile"),
            {
                "action": "update_profile",
                "first_name": "Updated",
                "last_name": "Name",
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
                "home_degree_program": student.home_degree_program,
                "year_level": student.year_level_id,
                "profile_photo": photo,
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

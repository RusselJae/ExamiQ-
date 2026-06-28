import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

STUDENT_SIGNUP_DATA = {
    "role": User.Role.STUDENT,
    "email": "newstudent@test.edu",
    "password1": "strongpass123!",
    "password2": "strongpass123!",
    "student_number": "123456789",
    "home_degree_program": User.HomeDegreeProgram.CS,
    "phone_number": "09123456789",
}


@pytest.mark.django_db
class TestSignupRoles:
    def test_student_signup_creates_active_student(self, client, year_level, program_section):
        data = {
            **STUDENT_SIGNUP_DATA,
            "year_level": year_level.pk,
            "section": program_section.pk,
        }
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.role == User.Role.STUDENT
        assert user.student_number == "123456789"
        assert user.phone_number == "09123456789"
        assert user.home_degree_program == User.HomeDegreeProgram.CS
        assert user.year_level_id == year_level.pk
        assert user.section_id == program_section.pk
        assert user.is_active is True
        assert user.approval_status == User.ApprovalStatus.APPROVED

    def test_faculty_signup_creates_pending_inactive_account(self, client, department):
        response = client.post(
            reverse("account_signup"),
            {
                "role": User.Role.PROFESSOR,
                "email": "newprof@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
                "department": department.pk,
                "employee_id": "EMP-2024-001",
                "phone_number": "09123456789",
            },
        )
        assert response.status_code == 302
        assert response.url.endswith("registered=pending")
        user = User.objects.get(email="newprof@test.edu")
        assert user.role == User.Role.PROFESSOR
        assert user.department_id == department.pk
        assert user.employee_id == "EMP-2024-001"
        assert user.is_active is False
        assert user.approval_status == User.ApprovalStatus.PENDING

    def test_faculty_signup_requires_employee_id(self, client, department):
        response = client.post(
            reverse("account_signup"),
            {
                "role": User.Role.PROFESSOR,
                "email": "noprof@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
                "department": department.pk,
                "employee_id": "",
                "phone_number": "09123456789",
            },
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="noprof@test.edu").exists()

    def test_student_signup_does_not_require_employee_id(self, client, year_level, program_section):
        data = {
            **STUDENT_SIGNUP_DATA,
            "year_level": year_level.pk,
            "section": program_section.pk,
            "employee_id": "",
        }
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.employee_id == ""

    def test_chairperson_signup_requires_department(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "role": User.Role.CHAIRPERSON,
                "email": "newchair@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
                "department": "",
                "employee_id": "EMP-CHAIR-01",
                "phone_number": "09123456789",
            },
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="newchair@test.edu").exists()

    def test_student_number_must_be_nine_digits(self, client, year_level):
        data = {
            **STUDENT_SIGNUP_DATA,
            "student_number": "12345",
            "year_level": year_level.pk,
        }
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    def test_pending_faculty_cannot_login(self, client, department):
        User.objects.create_user(
            email="pending@test.edu",
            password="strongpass123!",
            role=User.Role.PROFESSOR,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        response = client.post(
            reverse("account_login"),
            {"login": "pending@test.edu", "password": "strongpass123!"},
        )
        assert response.status_code == 302
        assert "registered=pending" in response.url


@pytest.mark.django_db
class TestAuthTemplates:
    def test_login_page_has_forgot_password(self, client):
        response = client.get(reverse("account_login"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "Forgot password?" in content
        assert reverse("account_reset_password") in content
        assert "auth-quick-access" not in content

    def test_signup_page_has_divider_and_placeholder(self, client):
        response = client.get(reverse("account_signup"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "auth-page__badge" not in content
        assert "auth-form__divider" in content
        assert "name@school.edu.ph" in content

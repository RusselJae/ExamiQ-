import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.users.models import Department, Program

User = get_user_model()

STUDENT_SIGNUP_DATA = {
    "role": User.Role.STUDENT,
    "email": "newstudent@test.edu",
    "password1": "strongpass123!",
    "password2": "strongpass123!",
    "first_name": "Ana",
    "last_name": "Santos",
    "middle_name": "",
    "suffix": "",
    "student_number": "123456789",
    "phone_number": "09123456789",
}


@pytest.fixture
def bsed_program(db):
    edu, _ = Department.objects.get_or_create(name="College of Education")
    program, _ = Program.objects.get_or_create(
        slug=User.HomeDegreeProgram.BSED_MATH,
        defaults={"name": "BSEd Mathematics", "managing_department": edu},
    )
    return program


def _student_data(**extra):
    return {**STUDENT_SIGNUP_DATA, **extra}


@pytest.mark.django_db
class TestSignupRoles:
    def test_student_signup_creates_active_student(
        self, client, bsed_program
    ):
        response = client.post(reverse("account_signup"), _student_data())
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.role == User.Role.STUDENT
        assert user.student_number == "123456789"
        assert user.phone_number == "09123456789"
        assert user.home_degree_program == User.HomeDegreeProgram.BSED_MATH
        assert user.year_level is None
        assert user.section is None
        assert user.is_active is True
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.first_name == "Ana"
        assert user.last_name == "Santos"

    def test_student_signup_accepts_optional_middle_name_and_suffix(
        self, client, bsed_program
    ):
        data = _student_data(
            email="namedstudent@test.edu",
            student_number="987654321",
            middle_name="Marie",
            suffix="Jr.",
        )
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        user = User.objects.get(email="namedstudent@test.edu")
        assert user.middle_name == "Marie"
        assert user.suffix == "Jr."
        assert user.get_full_name() == "Ana Marie Santos Jr."

    def test_student_signup_requires_first_and_last_name(
        self, client, bsed_program
    ):
        data = _student_data(first_name="", last_name="")
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    def test_faculty_signup_creates_active_approved_account(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "role": User.Role.PROFESSOR,
                "email": "newprof@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
                "first_name": "Rico",
                "last_name": "Cruz",
                "employee_id": "EMP-2024-001",
                "phone_number": "09123456789",
            },
        )
        assert response.status_code == 302
        user = User.objects.get(email="newprof@test.edu")
        assert user.role == User.Role.PROFESSOR
        assert user.department is not None
        assert user.department.name == "College of Education"
        assert user.employee_id == "EMP-2024-001"
        assert user.is_active is True
        assert user.approval_status == User.ApprovalStatus.APPROVED

    def test_faculty_signup_requires_employee_id(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "role": User.Role.PROFESSOR,
                "email": "noprof@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
                "first_name": "No",
                "last_name": "Prof",
                "employee_id": "",
                "phone_number": "09123456789",
            },
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="noprof@test.edu").exists()

    def test_student_signup_does_not_require_employee_id(
        self, client, bsed_program
    ):
        data = _student_data(employee_id="")
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.employee_id == ""

    def test_chairperson_role_not_available_on_signup(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "role": User.Role.CHAIRPERSON,
                "email": "newchair@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
                "first_name": "Chair",
                "last_name": "Person",
                "department": "",
                "employee_id": "EMP-CHAIR-01",
                "phone_number": "09123456789",
            },
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="newchair@test.edu").exists()

    def test_student_number_must_be_nine_digits(self, client):
        data = {**STUDENT_SIGNUP_DATA, "student_number": "12345"}
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
        assert "First name" in content
        assert "Middle name (optional)" in content
        assert "Suffix (optional)" in content
        assert "auth-password-strength--compact" in content
        assert "Employee ID" in content
        assert "Subjects (choose at least 3)" not in content
        assert "Program" not in content or "home_degree_program" not in content

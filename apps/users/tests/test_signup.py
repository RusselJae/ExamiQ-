import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.questions.models import YearLevel
from apps.users.models import AcademicYear, Department, Program, ProgramSection

User = get_user_model()


@pytest.fixture
def bsed_program(db):
    edu, _ = Department.objects.get_or_create(name="College of Education")
    program, _ = Program.objects.get_or_create(
        slug=User.HomeDegreeProgram.BSED_MATH,
        defaults={"name": "BSEd Mathematics", "managing_department": edu},
    )
    return program


@pytest.fixture
def signup_year_level(db):
    year, _ = YearLevel.objects.get_or_create(
        order=2,
        defaults={"name": "2nd Year"},
    )
    if year.name != "2nd Year":
        year.name = "2nd Year"
        year.save(update_fields=["name"])
    return year


@pytest.fixture
def signup_section(db, bsed_program, signup_year_level):
    academic_year, _ = AcademicYear.objects.get_or_create(
        label="2025-2026",
        defaults={"is_current": True},
    )
    if not academic_year.is_current:
        academic_year.is_current = True
        academic_year.save(update_fields=["is_current"])
    section, _ = ProgramSection.objects.get_or_create(
        program=bsed_program,
        year_level=signup_year_level,
        label="1M",
        academic_year=academic_year,
        defaults={"max_students": 40, "is_active": True},
    )
    return section


def _student_data(signup_year_level, signup_section, **extra):
    data = {
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
        "year_level": signup_year_level.pk,
        "section": signup_section.pk,
    }
    data.update(extra)
    return data


def _faculty_data(signup_year_level, signup_section, **extra):
    data = {
        "role": User.Role.PROFESSOR,
        "email": "newprof@test.edu",
        "password1": "strongpass123!",
        "password2": "strongpass123!",
        "first_name": "Rico",
        "last_name": "Cruz",
        "employee_id": "EMP-2024-001",
        "phone_number": "09123456789",
        "year_level": signup_year_level.pk,
        "section": signup_section.pk,
    }
    data.update(extra)
    return data


@pytest.mark.django_db
class TestSignupRoles:
    def test_student_signup_creates_active_student(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        response = client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.role == User.Role.STUDENT
        assert user.student_number == "123456789"
        assert user.phone_number == "09123456789"
        assert user.home_degree_program == User.HomeDegreeProgram.BSED_MATH
        assert user.year_level_id == signup_year_level.pk
        assert user.section_id == signup_section.pk
        assert user.is_active is True
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.first_name == "Ana"
        assert user.last_name == "Santos"

    def test_student_signup_accepts_optional_middle_name_and_suffix(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(
            signup_year_level,
            signup_section,
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
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(
            signup_year_level, signup_section, first_name="", last_name=""
        )
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    def test_student_signup_requires_year_and_section(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(signup_year_level, signup_section)
        data.pop("year_level")
        data.pop("section")
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    def test_faculty_signup_creates_active_approved_account(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        response = client.post(
            reverse("account_signup"),
            _faculty_data(signup_year_level, signup_section),
        )
        assert response.status_code == 302
        user = User.objects.get(email="newprof@test.edu")
        assert user.role == User.Role.PROFESSOR
        assert user.department is not None
        assert user.department.name == "College of Education"
        assert user.employee_id == "EMP-2024-001"
        assert user.is_active is True
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.year_level_id is None
        assert user.section_id is None
        assert list(user.assigned_sections.values_list("pk", flat=True)) == [
            signup_section.pk
        ]

    def test_faculty_signup_requires_year_and_section(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _faculty_data(signup_year_level, signup_section)
        data.pop("year_level")
        data.pop("section")
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newprof@test.edu").exists()

    def test_faculty_signup_requires_employee_id(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        response = client.post(
            reverse("account_signup"),
            _faculty_data(
                signup_year_level,
                signup_section,
                email="noprof@test.edu",
                employee_id="",
            ),
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="noprof@test.edu").exists()

    def test_student_signup_does_not_require_employee_id(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(signup_year_level, signup_section, employee_id="")
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.employee_id == ""

    def test_chairperson_role_not_available_on_signup(
        self, client, signup_year_level, signup_section
    ):
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
                "year_level": signup_year_level.pk,
                "section": signup_section.pk,
            },
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="newchair@test.edu").exists()

    def test_student_number_must_be_nine_digits(
        self, client, signup_year_level, signup_section
    ):
        data = _student_data(
            signup_year_level, signup_section, student_number="12345"
        )
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
        assert "id_year_level" in content
        assert "id_section" in content
        assert "Subjects (choose at least 3)" not in content
        assert "Program" not in content or "home_degree_program" not in content

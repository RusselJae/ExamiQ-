import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.urls import reverse

from apps.questions.models import YearLevel
from apps.users.models import AcademicYear, Department, Program, ProgramSection

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    """Keep allauth's signup rate limit from leaking across tests (429s)."""
    cache.clear()
    yield
    cache.clear()


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
    }
    data.update(extra)
    return data


FACULTY_TOKEN = "test-faculty-token-456"


def _otp_code_from_mailbox() -> str:
    body = mail.outbox[-1].body
    return next(token for token in body.split() if token.isdigit() and len(token) == 6)


@pytest.mark.django_db
class TestSignupRoles:
    @pytest.fixture(autouse=True)
    def _locmem_email(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.FACULTY_PORTAL_TOKEN = FACULTY_TOKEN

    def test_student_signup_creates_inactive_pending_otp(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        response = client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        assert response.status_code == 302
        assert reverse("users:signup_verify") in response.url
        user = User.objects.get(email="newstudent@test.edu")
        assert user.role == User.Role.STUDENT
        assert user.student_number == "123456789"
        assert user.phone_number == "09123456789"
        assert user.home_degree_program == User.HomeDegreeProgram.BSED_MATH
        assert user.year_level_id == signup_year_level.pk
        assert user.section_id == signup_section.pk
        assert user.is_active is False
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.first_name == "Ana"
        assert user.last_name == "Santos"
        assert len(mail.outbox) == 1
        assert "verification code" in mail.outbox[0].subject.lower()
        assert mail.outbox[0].alternatives
        html_body = mail.outbox[0].alternatives[0][0]
        assert "Confirm your email" in html_body
        assert "ExamiQ" in html_body

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
        assert user.is_active is False

    def test_student_signup_requires_first_and_last_name(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(
            signup_year_level, signup_section, first_name="", last_name=""
        )
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    @pytest.mark.parametrize(
        "field,value",
        [
            ("first_name", "Ana2"),
            ("first_name", "Ana_Marie"),
            ("last_name", "Santos#"),
            ("middle_name", "3Rose"),
        ],
    )
    def test_signup_rejects_digits_and_specials_in_names(
        self, client, bsed_program, signup_year_level, signup_section, field, value
    ):
        data = _student_data(signup_year_level, signup_section, **{field: value})
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    @pytest.mark.parametrize("field", ["first_name", "last_name", "middle_name"])
    def test_signup_rejects_names_over_100_characters(
        self, client, bsed_program, signup_year_level, signup_section, field
    ):
        data = _student_data(signup_year_level, signup_section, **{field: "A" * 101})
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    def test_signup_accepts_hyphens_spaces_and_apostrophes(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(
            signup_year_level,
            signup_section,
            email="names@test.edu",
            first_name="Mary-Jane",
            last_name="O'Neil",
            middle_name="de la Cruz",
        )
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        user = User.objects.get(email="names@test.edu")
        assert user.get_full_name() == "Mary-Jane de la Cruz O'Neil"

    def test_student_signup_requires_year_and_section(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _student_data(signup_year_level, signup_section)
        data.pop("year_level")
        data.pop("section")
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 200
        assert not User.objects.filter(email="newstudent@test.edu").exists()

    def test_faculty_signup_creates_inactive_pending_approval_request(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        response = client.post(
            reverse("account_faculty_signup", args=[FACULTY_TOKEN]),
            _faculty_data(signup_year_level, signup_section),
        )
        assert response.status_code == 302
        user = User.objects.get(email="newprof@test.edu")
        assert user.role == User.Role.PROFESSOR
        assert user.department is not None
        assert user.department.name == "College of Education"
        assert user.employee_id == "EMP-2024-001"
        assert user.is_active is False
        assert user.approval_status == User.ApprovalStatus.PENDING
        assert user.year_level_id is None
        assert user.section_id is None
        assert not user.assigned_sections.exists()
        assert len(mail.outbox) == 1

    def test_faculty_signup_does_not_accept_section_assignments(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        data = _faculty_data(
            signup_year_level,
            signup_section,
            assigned_sections=[signup_section.pk],
        )
        response = client.post(
            reverse("account_faculty_signup", args=[FACULTY_TOKEN]), data
        )
        assert response.status_code == 302
        user = User.objects.get(email="newprof@test.edu")
        assert not user.assigned_sections.exists()

    def test_otp_verify_activates_account(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        from allauth.account.models import EmailAddress

        client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        user = User.objects.get(email="newstudent@test.edu")
        assert user.is_active is False
        code = _otp_code_from_mailbox()
        response = client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": code},
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.is_active is True
        email_addr = EmailAddress.objects.get(user=user, email=user.email)
        assert email_addr.verified is True
        assert email_addr.primary is True

    def test_verified_student_can_login_without_500(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        from allauth.account.models import EmailAddress

        client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        code = _otp_code_from_mailbox()
        client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": code},
        )
        client.logout()

        user = User.objects.get(email="newstudent@test.edu")
        assert user.is_active is True
        assert EmailAddress.objects.filter(
            user=user, email=user.email, verified=True, primary=True
        ).exists()

        response = client.post(
            reverse("account_login"),
            {"login": "newstudent@test.edu", "password": "strongpass123!"},
        )
        assert response.status_code == 302
        assert response.status_code != 500
        assert "_auth_user_id" in client.session

    def test_student_signup_needs_no_faculty_activation(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        """Students sign up freely: the email OTP is the only step."""
        coordinator = User.objects.create_user(
            email="coordinator@test.edu",
            password="testpass123",
            role=User.Role.PROGRAM_COORDINATOR,
        )
        client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        user = User.objects.get(email="newstudent@test.edu")
        # No approval gate and no activation request mailed to the coordinator.
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.is_active is False
        assert len(mail.outbox) == 1
        assert "verification code" in mail.outbox[0].subject.lower()
        assert all(coordinator.email not in message.to for message in mail.outbox)

        # The OTP alone activates the account — no faculty action needed.
        code = _otp_code_from_mailbox()
        response = client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": code},
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.is_active is True
        assert user.approval_status == User.ApprovalStatus.APPROVED

    def test_otp_wrong_code_keeps_inactive(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        response = client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": "000000"},
        )
        assert response.status_code == 400
        user = User.objects.get(email="newstudent@test.edu")
        assert user.is_active is False

    def test_faculty_email_verification_keeps_account_pending(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        client.post(
            reverse("account_faculty_signup", args=[FACULTY_TOKEN]),
            _faculty_data(signup_year_level, signup_section),
        )
        code = _otp_code_from_mailbox()
        response = client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": code},
        )
        assert response.status_code == 302
        user = User.objects.get(email="newprof@test.edu")
        assert user.approval_status == User.ApprovalStatus.PENDING
        assert user.is_active is False

    def test_login_blocked_until_otp_verified(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        client.logout()
        response = client.post(
            reverse("account_login"),
            {"login": "newstudent@test.edu", "password": "strongpass123!"},
        )
        assert response.status_code == 302
        assert "verify_email" in response.url or "signup/verify" in response.url
        assert "_auth_user_id" not in client.session

    def test_faculty_signup_requires_employee_id(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        response = client.post(
            reverse("account_faculty_signup", args=[FACULTY_TOKEN]),
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
        assert user.is_active is False

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
        data = _student_data(signup_year_level, signup_section, student_number="12345")
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
class TestAlreadyRegisteredEmail:
    """A student who signed up but never verified must not hit a dead end."""

    @pytest.fixture(autouse=True)
    def _locmem_email(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.FACULTY_PORTAL_TOKEN = FACULTY_TOKEN

    def test_unverified_account_points_to_signin_and_resend(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        User.objects.create_user(
            email="newstudent@test.edu",
            password="strongpass123!",
            role=User.Role.STUDENT,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=False,
        )
        response = client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "already registered" in content
        assert "waiting for email verification" in content
        assert "Resend code" in content
        assert reverse("account_login") in content

    def test_active_account_points_to_signin(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        User.objects.create_user(
            email="newstudent@test.edu",
            password="strongpass123!",
            role=User.Role.STUDENT,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
        )
        response = client.post(
            reverse("account_signup"),
            _student_data(signup_year_level, signup_section),
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "already registered" in content
        assert "Sign in with it instead" in content

    def test_login_of_unverified_account_opens_verify_screen(
        self, client, bsed_program, signup_year_level, signup_section
    ):
        User.objects.create_user(
            email="newstudent@test.edu",
            password="strongpass123!",
            role=User.Role.STUDENT,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=False,
        )
        response = client.post(
            reverse("account_login"),
            {"login": "newstudent@test.edu", "password": "strongpass123!"},
        )
        assert response.status_code == 302
        assert reverse("users:signup_verify") in response.url

    def test_login_page_explains_pending_and_archived_states(self, client):
        pending = client.get(reverse("account_login") + "?registered=pending")
        assert pending.status_code == 200
        assert "waiting for email verification" in pending.content.decode()

        archived = client.get(reverse("account_login") + "?archived=1")
        assert archived.status_code == 200
        assert "archived" in archived.content.decode()

        verified = client.get(reverse("account_login") + "?verified=1")
        assert verified.status_code == 200
        assert "Email verified" in verified.content.decode()


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
        assert "Employee ID" not in content
        assert "id_year_level" in content
        assert "id_section" in content
        assert "Faculty signup PIN" not in content
        assert "Subjects (choose at least 3)" not in content
        assert "Program" not in content or "home_degree_program" not in content

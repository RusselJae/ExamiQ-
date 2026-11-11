"""Student role test cases — User Management and Performance Summary modules.

Maps to the manual test-case table ``docs/role-test-cases.md`` (Appendix A.1),
rows TC-S01, TC-S02, TC-S06 and TC-S07:

* TC-S01 Sign In
* TC-S02 Sign Up and email verification
* TC-S06 View Mistakes and answer detail
* TC-S07 Dashboard, session history and topic progress
"""

import pytest
from django.core import mail
from django.urls import reverse

from apps.analytics.models import MistakeRecord
from apps.questions.models import Question
from apps.reviews.models import ReviewSession
from apps.reviews.services import complete_session, start_review_session, submit_answer
from apps.users.models import User


def _otp_code_from_mailbox() -> str:
    body = mail.outbox[-1].body
    return next(token for token in body.split() if token.isdigit() and len(token) == 6)


def _student_signup_payload(year_level, section, **overrides):
    payload = {
        "role": User.Role.STUDENT,
        "email": "new.student@test.edu",
        "password1": "strongpass123!",
        "password2": "strongpass123!",
        "first_name": "Ana",
        "last_name": "Santos",
        "middle_name": "",
        "suffix": "",
        "student_number": "123456789",
        "phone_number": "09123456789",
        "year_level": year_level.pk if year_level else "",
        "section": section.pk if section else "",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestStudentSignIn:
    """TC-S01 — Sign in and role-based landing."""

    def test_student_sign_in_redirects_to_dashboard(self, client, bsed_student):
        response = client.post(
            reverse("account_login"),
            {"login": bsed_student.email, "password": "testpass123"},
        )

        assert response.status_code == 302
        assert response.url == reverse("analytics_student:dashboard")

    def test_sign_in_with_wrong_password_is_rejected(self, client, bsed_student):
        """Actual error: invalid credentials."""
        response = client.post(
            reverse("account_login"),
            {"login": bsed_student.email, "password": "wrong-password"},
        )

        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_anonymous_student_page_redirects_to_login(self, client):
        """Actual error: not authenticated."""
        response = client.get(reverse("analytics_student:dashboard"))

        assert response.status_code == 302
        assert reverse("account_login") in response.url

    def test_faculty_cannot_open_student_dashboard(self, client, professor):
        """Actual error: role mismatch."""
        client.force_login(professor)

        response = client.get(reverse("analytics_student:dashboard"))

        assert response.status_code == 403


@pytest.mark.django_db
class TestStudentSignUp:
    """TC-S02 — Sign up and email OTP verification."""

    @pytest.fixture(autouse=True)
    def _locmem_email(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    @pytest.fixture(autouse=True)
    def _register_signup_number(self, db):
        from apps.users.models import PendingStudentRegistration

        PendingStudentRegistration.objects.get_or_create(student_number="123456789")

    def test_signup_creates_inactive_account_pending_verification(
        self, client, year_level, bsed_section
    ):
        response = client.post(
            reverse("account_signup"),
            _student_signup_payload(year_level, bsed_section),
        )

        assert response.status_code == 302
        assert reverse("users:signup_verify") in response.url
        user = User.objects.get(email="new.student@test.edu")
        assert user.is_active is False
        assert user.role == User.Role.STUDENT
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.home_degree_program == User.HomeDegreeProgram.BSED_MATH

    def test_otp_verification_activates_account(self, client, year_level, bsed_section):
        client.post(
            reverse("account_signup"),
            _student_signup_payload(year_level, bsed_section),
        )

        response = client.post(
            reverse("users:signup_verify"),
            {"action": "verify", "code": _otp_code_from_mailbox()},
        )

        assert response.status_code == 302
        user = User.objects.get(email="new.student@test.edu")
        assert user.is_active is True

    def test_signup_rejects_duplicate_student_number(
        self, client, year_level, bsed_section, bsed_student
    ):
        """Actual error: student number already registered."""
        bsed_student.student_number = "123456789"
        bsed_student.save(update_fields=["student_number"])

        response = client.post(
            reverse("account_signup"),
            _student_signup_payload(year_level, bsed_section),
        )

        assert response.status_code == 200
        assert "This student number is already registered." in response.content.decode()
        assert not User.objects.filter(email="new.student@test.edu").exists()

    def test_signup_requires_a_section(self, client, year_level):
        """Actual error: incomplete profile."""
        response = client.post(
            reverse("account_signup"),
            _student_signup_payload(year_level, None),
        )

        assert response.status_code == 200
        assert "Section is required." in response.context["form"].errors.as_text()
        assert not User.objects.filter(email="new.student@test.edu").exists()

    def test_signup_requires_a_year_level(self, client, bsed_section):
        """Actual error: incomplete profile."""
        response = client.post(
            reverse("account_signup"),
            _student_signup_payload(None, bsed_section),
        )

        assert response.status_code == 200
        assert "Year level is required." in response.context["form"].errors.as_text()
        assert not User.objects.filter(email="new.student@test.edu").exists()

    def test_signup_rejects_section_from_another_year_level(self, client, bsed_section):
        """Actual error: section does not match the selected year level."""
        from apps.questions.models import YearLevel

        other_year = YearLevel.objects.create(order=7, name="4th Year")

        response = client.post(
            reverse("account_signup"),
            _student_signup_payload(other_year, bsed_section),
        )

        assert response.status_code == 200
        assert "Select a valid choice" in response.context["form"].errors.as_text()
        assert not User.objects.filter(email="new.student@test.edu").exists()


@pytest.mark.django_db
class TestStudentMistakes:
    """TC-S06 — Mistake tracking and answer detail."""

    @pytest.fixture
    def answered_session(self, bsed_student, bsed_mcq_question):
        question, _ = bsed_mcq_question
        session = start_review_session(
            student=bsed_student,
            topic=question.topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=30,
        )
        wrong = question.choices.filter(is_correct=False).first()
        submit_answer(
            session=session,
            question=question,
            confidence=1,
            selected_choice=wrong,
            time_spent_seconds=9,
        )
        complete_session(session)
        return session

    def test_mistake_list_shows_own_mistake(
        self, client, bsed_student, answered_session
    ):
        client.force_login(bsed_student)

        response = client.get(reverse("analytics_student:mistakes"))

        assert response.status_code == 200
        assert list(response.context["mistakes"]) == list(
            MistakeRecord.objects.filter(student=bsed_student)
        )
        assert response.context["mistakes"].exists()

    def test_answer_detail_is_visible_to_the_owner(
        self, client, bsed_student, answered_session
    ):
        answer = answered_session.answers.get()
        client.force_login(bsed_student)

        response = client.get(
            reverse("analytics_student:answer_detail", kwargs={"answer_pk": answer.pk})
        )

        assert response.status_code == 200
        assert response.context["answer"].pk == answer.pk

    def test_answer_detail_is_hidden_from_other_students(
        self, client, student, answered_session
    ):
        """Actual error: answer belongs to another student."""
        answer = answered_session.answers.get()
        client.force_login(student)

        response = client.get(
            reverse("analytics_student:answer_detail", kwargs={"answer_pk": answer.pk})
        )

        assert response.status_code == 404

    def test_mistake_list_excludes_other_students_mistakes(
        self, client, student, answered_session
    ):
        client.force_login(student)

        response = client.get(reverse("analytics_student:mistakes"))

        assert response.status_code == 200
        assert not response.context["mistakes"].exists()


@pytest.mark.django_db
class TestStudentPerformanceSummary:
    """TC-S07 — Dashboard, session history and topic progress."""

    @pytest.fixture
    def completed_session(self, bsed_student, bsed_mcq_question):
        question, _ = bsed_mcq_question
        session = start_review_session(
            student=bsed_student,
            topic=question.topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=30,
        )
        return complete_session(session)

    def test_dashboard_renders_with_zero_state_metrics(self, client, bsed_student):
        client.force_login(bsed_student)

        response = client.get(reverse("analytics_student:dashboard"))

        assert response.status_code == 200
        assert "summary" in response.context

    def test_session_history_lists_only_own_sessions(
        self, client, bsed_student, student, completed_session
    ):
        client.force_login(bsed_student)

        response = client.get(reverse("analytics_student:session_history"))

        assert response.status_code == 200
        sessions = list(response.context["sessions"])
        assert [s.pk for s in sessions] == [completed_session.pk]

    def test_session_history_hides_other_students_sessions(
        self, client, student, completed_session
    ):
        client.force_login(student)

        response = client.get(reverse("analytics_student:session_history"))

        assert response.status_code == 200
        assert not list(response.context["sessions"])

    def test_topic_progress_renders(self, client, bsed_student, completed_session):
        client.force_login(bsed_student)

        response = client.get(reverse("analytics_student:topic_progress"))

        assert response.status_code == 200
        assert "topics" in response.context

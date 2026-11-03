"""Faculty (Professor) role test cases — User Management, Exam Configuration
and Performance Summary modules.

Maps to the manual test-case table ``docs/role-test-cases.md`` (Appendix A.2),
rows TC-F01, TC-F02, TC-F06 and TC-F07:

* TC-F01 Sign In
* TC-F02 Course catalog and course analytics
* TC-F06 Configure exam setup (per-question timer)
* TC-F07 Student roster and course heatmap
"""

import pytest
from django.urls import reverse

from apps.questions.models import Question
from apps.reviews.models import ExamSetup
from apps.users.models import Course, User


@pytest.mark.django_db
class TestFacultySignIn:
    """TC-F01 — Sign in and role-based landing."""

    def test_faculty_sign_in_redirects_to_faculty_overview(
        self, client, professor, settings
    ):
        settings.LOGIN_OTP_EXEMPT_EMAILS = {professor.email}

        response = client.post(
            reverse("account_login"),
            {"login": professor.email, "password": "testpass123"},
        )

        assert response.status_code == 302
        assert response.url == reverse("analytics_professor:overview")

    def test_faculty_sign_in_requires_the_email_code_by_default(
        self, client, professor, settings
    ):
        """Actual error: faculty sign-in needs the emailed code."""
        settings.LOGIN_OTP_EXEMPT_EMAILS = set()

        response = client.post(
            reverse("account_login"),
            {"login": professor.email, "password": "testpass123"},
        )

        assert response.status_code == 302
        assert response.url == "/accounts/login/code/confirm/"
        assert "_auth_user_id" not in client.session

    def test_faculty_cannot_open_the_student_dashboard(self, client, professor):
        """Actual error: role mismatch."""
        client.force_login(professor)

        response = client.get(reverse("analytics_student:dashboard"))

        assert response.status_code == 403

    def test_faculty_cannot_open_the_coordinator_console(self, client, professor):
        """Actual error: role mismatch."""
        client.force_login(professor)

        response = client.get(reverse("campus:dashboard"))

        assert response.status_code == 403


@pytest.mark.django_db
class TestFacultyCourseCatalog:
    """TC-F02 — Course catalog and course analytics."""

    def test_course_list_renders(self, client, professor, teaching_assignment):
        client.force_login(professor)

        response = client.get(reverse("analytics_professor:course_list"))

        assert response.status_code == 200
        assert response.context["course_cards"]

    def test_course_detail_renders_for_an_owned_course(
        self, client, professor, teaching_assignment
    ):
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )

        assert response.status_code == 200
        assert response.context["course"].pk == course.pk

    def test_course_detail_is_hidden_from_another_professor(
        self, client, professor, teaching_assignment
    ):
        """Actual error: course owned by another faculty member."""
        other_professor = User.objects.create_user(
            email="other.prof@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=professor.department,
        )
        course = teaching_assignment.course
        course.professor = other_professor
        course.save(update_fields=["professor"])
        client.force_login(professor)

        response = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )

        assert response.status_code == 404

    def test_faculty_cannot_create_curriculum_subjects(self, client, professor):
        """Actual error: subject creation belongs to the program coordinator."""
        client.force_login(professor)

        response = client.get(reverse("analytics_professor:course_create"))

        assert response.status_code == 403


@pytest.mark.django_db
class TestFacultyExamSetup:
    """TC-F06 — Configure the per-question exam timer."""

    def test_exam_setup_form_renders(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.get(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        )

        assert response.status_code == 200

    def test_saving_exam_setup_stores_the_timer(
        self, client, professor, teaching_assignment
    ):
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.post(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk}),
            {
                "is_enabled": "on",
                "seconds_per_question": 45,
                "allowed_difficulties": [Question.Difficulty.EASY],
                "topics": [],
            },
        )

        assert response.status_code == 302
        setup = ExamSetup.objects.get(course=course)
        assert setup.seconds_per_question == 45
        assert setup.is_enabled is True

    def test_timer_outside_the_allowed_range_is_rejected(
        self, client, professor, teaching_assignment
    ):
        """Actual error: timer below the 10 second floor."""
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.post(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk}),
            {
                "is_enabled": "on",
                "seconds_per_question": 5,
                "allowed_difficulties": [Question.Difficulty.EASY],
                "topics": [],
            },
        )

        assert response.status_code == 200
        assert (
            "Seconds per question must be between 10 and 120."
            in response.content.decode()
        )
        setup = ExamSetup.objects.get(course=course)
        assert setup.seconds_per_question != 5

    def test_at_least_one_difficulty_is_required(
        self, client, professor, teaching_assignment
    ):
        """Actual error: no difficulty selected."""
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.post(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk}),
            {
                "is_enabled": "on",
                "seconds_per_question": 30,
                "allowed_difficulties": [],
                "topics": [],
            },
        )

        assert response.status_code == 200
        assert "Select at least one difficulty level." in response.content.decode()

    def test_exam_setup_is_hidden_from_another_professor(
        self, client, professor, teaching_assignment
    ):
        """Actual error: course owned by another faculty member."""
        course = teaching_assignment.course
        other_professor = User.objects.create_user(
            email="other.prof2@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=professor.department,
        )
        client.force_login(other_professor)

        response = client.get(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestFacultyStudentRoster:
    """TC-F07 — Student roster, student detail and course heatmap."""

    @pytest.fixture
    def scoped_professor(self, professor, program_section, subject):
        """Faculty with an explicit roster scope (sections + subjects)."""
        professor.assigned_sections.add(program_section)
        professor.assigned_subjects.add(subject)
        return professor

    def test_student_list_renders(self, client, scoped_professor):
        client.force_login(scoped_professor)

        response = client.get(reverse("analytics_professor:students"))

        assert response.status_code == 200

    def test_course_heatmap_renders(
        self, client, scoped_professor, teaching_assignment
    ):
        course = teaching_assignment.course
        client.force_login(scoped_professor)

        response = client.get(
            reverse("analytics_professor:course_heatmap", kwargs={"pk": course.pk})
        )

        assert response.status_code == 200

    def test_student_detail_is_hidden_for_an_out_of_scope_student(
        self, client, scoped_professor, student
    ):
        """Actual error: student has no completed exams for this faculty."""
        client.force_login(scoped_professor)

        response = client.get(
            reverse(
                "analytics_professor:professor_student_detail",
                kwargs={"student_pk": student.pk},
            )
        )

        assert response.status_code == 404

    def test_legacy_section_roster_is_retired(
        self, client, scoped_professor, program_section
    ):
        """Actual error: roster screen retired — returns 404 for everyone."""
        client.force_login(scoped_professor)

        response = client.get(
            reverse(
                "analytics_professor:section_roster",
                kwargs={"section_pk": program_section.pk},
            )
        )

        assert response.status_code == 404


@pytest.mark.django_db
def test_faculty_course_archive_marks_the_offering_archived(
    client, professor, teaching_assignment
):
    """TC-F02 — archiving a course offering keeps it out of the active list."""
    course = teaching_assignment.course
    client.force_login(professor)

    response = client.post(
        reverse("analytics_professor:course_archive", kwargs={"pk": course.pk})
    )

    assert response.status_code == 302
    course.refresh_from_db()
    assert course.is_archived is True
    assert Course.objects.filter(pk=course.pk).exists()

"""Faculty course home + tabs + banner UI (Overview / Content / Questions)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.users.assignment_services import get_or_create_catalog_course


@pytest.mark.django_db
class TestCourseHomeUI:
    def _catalog(self, client, professor, subject, bsed_program):
        subject.program = bsed_program
        subject.save(update_fields=["program"])
        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)
        return course

    def test_course_home_shows_banner_tabs_and_panel(
        self, client, professor, subject, bsed_program
    ):
        course = self._catalog(client, professor, subject, bsed_program)
        response = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )
        content = response.content.decode()
        assert response.status_code == 200
        # Tabs-only panel at the top (no banner in the panel).
        assert "course-tabs" in content
        assert "course-tab--overview" in content
        assert "course-tab--content" in content
        assert "course-tab--questions" in content
        assert "course-tab--level" not in content
        # Banner is not part of the panel; tabs sit at top only.
        assert "course-banner__name" not in content
        # One wrapping panel holds every grid, card, and label.
        assert "course-home-panel" in content
        # Content + questions stats (enrolled-students KPI removed by design).
        assert "Content" in content
        assert "Questions" in content
        assert "Enrolled students" not in content
        # Question breakdown (questions data) replaced the workflow.
        assert "Question Breakdown" in content
        assert "Questions data" in content
        assert "Interventions" in content

    def test_course_home_drops_workflow_and_quick_actions(
        self, client, professor, subject, bsed_program
    ):
        course = self._catalog(client, professor, subject, bsed_program)
        response = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )
        content = response.content.decode()
        assert response.status_code == 200
        # Quick actions + workflow are gone.
        assert 'data-content-modal="add"' not in content
        assert "course-home-actions" not in content
        assert "course-workflow" not in content
        assert "Upload content" not in content
        assert "Validate and publish" not in content
        # Retired KPI cards and analytics panels stay removed.
        assert "Sessions completed" not in content
        assert "Average score" not in content
        assert "Calibration" not in content
        assert "Misconception Topics" not in content
        # Cream 2px border + 25% rounding applied to the panel.
        assert "course-home-panel" in content

    def test_content_tab_links_from_course_home(
        self, client, professor, subject, bsed_program
    ):
        course = self._catalog(client, professor, subject, bsed_program)
        response = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )
        assert (
            reverse(
                "analytics_professor:material_list", kwargs={"course_pk": course.pk}
            )
            in response.content.decode()
        )

    def test_content_tab_marks_active_tab(
        self, client, professor, subject, bsed_program
    ):
        course = self._catalog(client, professor, subject, bsed_program)
        response = client.get(
            reverse(
                "analytics_professor:material_list", kwargs={"course_pk": course.pk}
            )
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "course-tab--content course-tab--active" in content
        # Banner is hidden on the content page (panel shows tabs only).
        assert "course-banner__code-chip" not in content
        # The library lives inside the wrapping panel.
        assert "course-home-panel" in content
        assert "materials-library" in content

    def test_questions_tab_marks_active_tab(
        self, client, professor, subject, bsed_program
    ):
        course = self._catalog(client, professor, subject, bsed_program)
        response = client.get(
            reverse(
                "analytics_professor:question_list", kwargs={"course_pk": course.pk}
            )
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "course-tab--questions course-tab--active" in content
        # The questions board lives inside the wrapping panel.
        assert "course-home-panel" in content
        assert "questions-page" in content

    def test_no_level_tab_on_any_course_page(
        self, client, professor, subject, bsed_program
    ):
        """The Level tab was removed; the three tabs render everywhere."""
        course = self._catalog(client, professor, subject, bsed_program)
        heatmap = client.get(
            reverse("analytics_professor:course_heatmap", kwargs={"pk": course.pk})
        ).content.decode()
        assert "course-tab--level" not in heatmap
        assert "course-tab--overview" in heatmap
        assert "course-tab--content" in heatmap
        assert "course-tab--questions" in heatmap

    def test_section_view_filters_enrolled_count(
        self, client, professor, subject, bsed_program, topic, academic_year
    ):
        """?section= scopes the enrolled-students card to that section."""
        from apps.reviews.models import ReviewSession
        from apps.users.models import Course, User

        subject.program = bsed_program
        subject.save(update_fields=["program"])
        section_a = Course.objects.create(
            program=bsed_program,
            code="BSEM 21",
            name="History of Mathematics",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="A",
        )
        section_b = Course.objects.create(
            program=bsed_program,
            code="BSEM 21",
            name="History of Mathematics",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="B",
        )
        student_a = User.objects.create_user(
            email="section.a@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
        )
        student_b = User.objects.create_user(
            email="section.b@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
        )
        from apps.users.models import AcademicYear, StudentFacultyAssignment

        year = AcademicYear.get_current() or academic_year
        assert year is not None
        for handled_student in (student_a, student_b):
            StudentFacultyAssignment.objects.create(
                student=handled_student,
                faculty=professor,
                subject=topic.subject,
                academic_year=year,
            )
        for student, course in ((student_a, section_a), (student_b, section_b)):
            ReviewSession.objects.create(
                student=student,
                topic=topic,
                difficulty="easy",
                course=course,
                status=ReviewSession.Status.COMPLETED,
            )
        client.force_login(professor)

        url = reverse("analytics_professor:course_detail", kwargs={"pk": section_a.pk})
        response = client.get(url)
        assert response.status_code == 200
        overview = response.content.decode()
        # Section tabs were removed: the course shows aggregate content only.
        assert "viewing-bar" not in overview
        assert "All sections" not in overview

        scoped_response = client.get(url + "?section=A")
        assert scoped_response.status_code == 200
        scoped = scoped_response.content.decode()
        assert "section-info-strip" not in scoped
        # The enrolled-students card was removed; the count lives in context.
        assert "Enrolled students" not in scoped
        assert scoped_response.context["selected_section"] == "A"
        assert scoped_response.context["summary"]["enrolled_count"] == 1

        combined_response = client.get(url)
        assert combined_response.context["selected_section"] == ""
        assert combined_response.context["summary"]["enrolled_count"] == 2

    def test_single_section_has_no_viewing_bar(
        self, client, professor, subject, bsed_program
    ):
        """Catalog courses show aggregate content with no section tabs."""
        course = self._catalog(client, professor, subject, bsed_program)
        content = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        ).content.decode()
        assert "viewing-bar" not in content
        assert "All sections" not in content
        assert "section-info-strip" not in content

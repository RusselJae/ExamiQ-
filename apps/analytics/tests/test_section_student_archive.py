import pytest
from django.urls import reverse

from apps.analytics.services import get_section_roster_summaries
from apps.users.assignment_services import archive_section_student
from apps.users.models import ProgramSection


@pytest.mark.django_db
class TestSectionStudentArchive:
    def test_faculty_archives_student_in_assigned_section(
        self, client, professor, student, program_section
    ):
        professor.assigned_sections.add(program_section)
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:section_student_archive",
                kwargs={
                    "section_pk": program_section.pk,
                    "student_pk": student.pk,
                },
            )
        )
        assert response.status_code == 302
        assert reverse("analytics_professor:students") in response.url

        student.refresh_from_db()
        assert student.is_archived is True
        assert student.is_active is False

        roster = get_section_roster_summaries(program_section)
        assert not any(row["student"].pk == student.pk for row in roster)

    def test_archived_student_hidden_until_show_archived_filter(
        self, client, professor, student, program_section
    ):
        professor.assigned_sections.add(program_section)
        archive_section_student(professor, program_section, student)

        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:section_roster",
                kwargs={"section_pk": program_section.pk},
            )
        )
        assert response.status_code == 404

        response = client.get(
            reverse(
                "analytics_professor:section_roster",
                kwargs={"section_pk": program_section.pk},
            )
            + "?show_archived=1"
        )
        assert response.status_code == 404

    def test_archived_student_cannot_log_in(self, professor, student, program_section):
        professor.assigned_sections.add(program_section)
        archive_section_student(professor, program_section, student)

        from django.contrib.auth import authenticate

        auth_user = authenticate(email=student.email, password="testpass123")
        assert auth_user is None

    def test_faculty_outside_assigned_section_gets_404(
        self, client, professor, student, program_section, bsed_program, year_level, academic_year
    ):
        other_section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="9Z",
            academic_year=academic_year,
            max_students=40,
        )
        professor.assigned_sections.add(other_section)
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:section_student_archive",
                kwargs={
                    "section_pk": program_section.pk,
                    "student_pk": student.pk,
                },
            )
        )
        assert response.status_code == 404

        student.refresh_from_db()
        assert student.is_archived is False

    def test_restore_student_returns_to_roster_and_login(
        self, client, professor, student, program_section
    ):
        professor.assigned_sections.add(program_section)
        archive_section_student(professor, program_section, student)

        client.force_login(professor)
        response = client.post(
            reverse(
                "analytics_professor:section_student_restore",
                kwargs={
                    "section_pk": program_section.pk,
                    "student_pk": student.pk,
                },
            )
        )
        assert response.status_code == 302
        assert reverse("analytics_professor:students") in response.url

        student.refresh_from_db()
        assert student.is_archived is False
        assert student.is_active is True

        roster = get_section_roster_summaries(program_section)
        assert any(row["student"].pk == student.pk for row in roster)

        from django.contrib.auth import authenticate

        auth_user = authenticate(email=student.email, password="testpass123")
        assert auth_user is not None

    def test_students_page_hides_archived_student(
        self, client, professor, student, program_section, subject, topic, course
    ):
        from apps.reviews.models import ReviewSession
        from apps.reviews.services import start_review_session

        professor.assigned_sections.add(program_section)
        professor.assigned_subjects.add(subject)

        session = start_review_session(
            student=student,
            topic=topic,
            difficulty="easy",
            course=course,
            subjects=[subject],
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        archive_section_student(professor, program_section, student)

        client.force_login(professor)
        list_resp = client.get(reverse("analytics_professor:students"))
        assert list_resp.status_code == 200
        assert student.email not in list_resp.content.decode()

        archived_resp = client.get(
            reverse("analytics_professor:students") + "?show_archived=1"
        )
        assert archived_resp.status_code == 200
        assert student.email in archived_resp.content.decode()
        assert "Restore" in archived_resp.content.decode()

    def test_students_page_shows_section_column(
        self, client, professor, student, program_section, subject, topic, course
    ):
        from apps.reviews.models import ReviewSession
        from apps.reviews.services import start_review_session

        professor.assigned_sections.add(program_section)
        professor.assigned_subjects.add(subject)

        session = start_review_session(
            student=student,
            topic=topic,
            difficulty="easy",
            course=course,
            subjects=[subject],
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        client.force_login(professor)
        response = client.get(reverse("analytics_professor:students"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Section" in content
        assert program_section.display_label in content

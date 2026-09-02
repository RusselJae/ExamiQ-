import pytest
from django.urls import reverse

from apps.analytics.services import (
    section_performance_summary,
    subject_performance_summary,
)
from apps.questions.models import Question, QuestionChoice, Subject, Topic
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.services import start_review_session, submit_answer
from apps.users.models import ProgramSection, User
from conftest import make_bsed_student


@pytest.mark.django_db
class TestSectionAndSubjectAnalytics:
    def test_section_summary_includes_any_subject_answered(
        self, student, professor, bsed_program, year_level, academic_year, course
    ):
        make_bsed_student(student, bsed_program=bsed_program, course=course)
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="2M",
            academic_year=academic_year,
            max_students=40,
        )
        student.section = section
        student.save(update_fields=["section_id"])

        subject = Subject.objects.create(
            program=bsed_program,
            code="GNED-X",
            name="Gen Ed",
            year_level=year_level,
            semester=1,
        )
        topic = Topic.objects.create(subject=subject, name="Intro")
        q = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Q?",
            status=Question.Status.APPROVED,
        )
        correct = QuestionChoice.objects.create(
            question=q, label="A", text="yes", is_correct=True
        )
        QuestionChoice.objects.create(question=q, label="B", text="no", is_correct=False)

        session = start_review_session(
            student,
            topic,
            Question.Difficulty.EASY,
            course=course,
            question_queue=[q.pk],
            subjects=[subject],
        )
        submit_answer(session, q, confidence=3, selected_choice=correct)
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        summary = section_performance_summary(section)
        assert summary["enrolled_count"] == 1
        codes = {row["code"] for row in summary["subject_breakdown"]}
        assert "GNED-X" in codes

        client_summary = subject_performance_summary(subject)
        assert client_summary["enrolled_count"] == 1
        assert client_summary["total_answers"] == 1

    def test_courses_list_shows_catalog_grid(
        self, client, professor, bsed_program, year_level
    ):
        Subject.objects.create(
            program=bsed_program,
            code="CAT-1",
            name="Catalog One",
            year_level=year_level,
            semester=1,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_list"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "CAT-1" in content
        assert "Clone to 2nd Sem" not in content
        assert "Course subjects" in content
        assert "course-subjects-table" in content
        assert "Questions" in content

    def test_section_nav_links_to_section_detail(
        self, client, professor, bsed_program, year_level, academic_year
    ):
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="1M",
            academic_year=academic_year,
            max_students=40,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:section_detail", kwargs={"pk": section.pk}))
        assert response.status_code == 404

    def test_professor_can_add_catalog_course(
        self, client, professor, year_level, bsed_program
    ):
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:course_create"),
            {
                "code": "BSEM 99",
                "name": "New Catalog Course",
                "year_level": year_level.pk,
                "semester": 1,
            },
        )
        assert response.status_code == 302
        assert Subject.objects.filter(program=bsed_program, code="BSEM 99").exists()


@pytest.mark.django_db
class TestSectionRosterAndStudentDetail:
    def test_section_roster_lists_enrolled_without_practice(
        self, client, professor, student, bsed_program, year_level, academic_year
    ):
        from apps.analytics.services import get_section_roster_summaries

        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="3M",
            academic_year=academic_year,
            max_students=40,
        )
        student.section = section
        student.role = User.Role.STUDENT
        student.save(update_fields=["section_id", "role"])

        roster = get_section_roster_summaries(section)
        assert any(row["student"].pk == student.pk for row in roster)
        row = next(r for r in roster if r["student"].pk == student.pk)
        assert row["questions_answered"] == 0
        assert row["subjects_taken"] == []
        assert row["sessions_completed"] == 0

        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:section_roster",
                kwargs={"section_pk": section.pk},
            )
        )
        assert response.status_code == 404

        detail = client.get(
            reverse(
                "analytics_professor:section_student_detail",
                kwargs={"section_pk": section.pk, "student_pk": student.pk},
            )
        )
        assert detail.status_code == 404

    def test_section_roster_unique_subjects_and_question_count(
        self, student, professor, bsed_program, year_level, academic_year, course
    ):
        from apps.analytics.services import get_section_roster_summaries

        make_bsed_student(student, bsed_program=bsed_program, course=course)
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="4M",
            academic_year=academic_year,
            max_students=40,
        )
        student.section = section
        student.save(update_fields=["section_id"])

        subject = Subject.objects.create(
            program=bsed_program,
            code="GNED 03",
            name="Math Modern World",
            year_level=year_level,
            semester=1,
        )
        topic = Topic.objects.create(subject=subject, name="Sets")
        questions = []
        for i in range(3):
            q = Question.objects.create(
                topic=topic,
                difficulty=Question.Difficulty.EASY,
                question_type=Question.QuestionType.MCQ,
                stem=f"Q{i}?",
                status=Question.Status.APPROVED,
            )
            QuestionChoice.objects.create(
                question=q, label="A", text="yes", is_correct=True
            )
            QuestionChoice.objects.create(
                question=q, label="B", text="no", is_correct=False
            )
            questions.append(q)

        session = start_review_session(
            student,
            topic,
            Question.Difficulty.EASY,
            course=course,
            question_queue=[q.pk for q in questions],
            subjects=[subject],
        )
        for q in questions:
            submit_answer(
                session,
                q,
                confidence=4,
                selected_choice=q.choices.get(is_correct=True),
            )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        roster = get_section_roster_summaries(section)
        row = next(r for r in roster if r["student"].pk == student.pk)
        assert row["subjects_taken"] == ["GNED 03"]
        assert row["subjects_taken_count"] == 1
        assert row["questions_answered"] == 3

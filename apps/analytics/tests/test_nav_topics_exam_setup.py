import pytest
from django.urls import reverse

from apps.questions.models import Question, QuestionChoice, Subject, Topic
from apps.questions.views_professor import topics_for_course_subject
from apps.reviews.exam_setup_services import (
    get_or_create_section_exam_setup,
    subjects_available_for_student,
)
from apps.reviews.models import SectionExamSetup
from apps.users.assignment_services import get_or_create_catalog_course
from apps.users.models import ProgramSection, User
from conftest import make_bsed_student


@pytest.mark.django_db
class TestCourseTopicScope:
    def test_catalog_topics_exclude_other_subjects(
        self, professor, bsed_program, year_level
    ):
        gned = Subject.objects.create(
            program=bsed_program,
            code="GNED 03",
            name="Math in Modern World",
            year_level=year_level,
            semester=1,
        )
        bsem = Subject.objects.create(
            program=bsed_program,
            code="BSEM 21",
            name="History of Math",
            year_level=year_level,
            semester=1,
        )
        Topic.objects.create(subject=gned, name="Sets")
        Topic.objects.create(subject=bsem, name="History Intro")
        course = get_or_create_catalog_course(professor, gned)
        names = list(
            topics_for_course_subject(course, professor).values_list("name", flat=True)
        )
        assert "Sets" in names
        assert "History Intro" not in names

    def test_course_open_lands_on_topics(
        self, client, professor, bsed_program, year_level
    ):
        subject = Subject.objects.create(
            program=bsed_program,
            code="OPEN-1",
            name="Open Course",
            year_level=year_level,
            semester=1,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_list"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "OPEN-1" in content
        assert "Course subjects" in content
        assert "course-subjects-table" in content
        assert "Questions" in content
        assert "Saved Questions" not in content or "Open" in content
        course = get_or_create_catalog_course(professor, subject)
        topics = client.get(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course.pk})
        )
        assert topics.status_code == 200
        assert "OPEN-1 Catalog" in topics.content.decode() or "Topics" in topics.content.decode()


@pytest.mark.django_db
class TestSectionExamSetupGating:
    def test_enabled_setup_restricts_student_subjects(
        self, student, professor, bsed_program, year_level, academic_year
    ):
        make_bsed_student(student, bsed_program=bsed_program)
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="9M",
            academic_year=academic_year,
            max_students=40,
        )
        student.section = section
        student.year_level = year_level
        student.save(update_fields=["section_id", "year_level_id"])

        s1 = Subject.objects.create(
            program=bsed_program, code="G1", name="One", year_level=year_level, semester=1
        )
        Subject.objects.create(
            program=bsed_program, code="G2", name="Two", year_level=year_level, semester=1
        )
        setup = get_or_create_section_exam_setup(section)
        setup.is_enabled = True
        setup.save(update_fields=["is_enabled"])
        setup.subjects.set([s1])

        codes = set(subjects_available_for_student(student).values_list("code", flat=True))
        assert codes == {"G1"}

    def test_section_exam_setup_view_saves(
        self, client, professor, bsed_program, year_level, academic_year
    ):
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="8M",
            academic_year=academic_year,
            max_students=40,
        )
        s1 = Subject.objects.create(
            program=bsed_program, code="S1", name="Sub1", year_level=year_level, semester=1
        )
        s2 = Subject.objects.create(
            program=bsed_program, code="S2", name="Sub2", year_level=year_level, semester=1
        )
        client.force_login(professor)
        url = reverse(
            "analytics_professor:section_exam_setup",
            kwargs={"section_pk": section.pk},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert "multi-select" in response.content.decode()

        response = client.post(
            url,
            {
                "is_enabled": "on",
                "seconds_per_question": 40,
                "subjects": [s1.pk, s2.pk],
                "allowed_difficulties": ["easy", "medium"],
            },
        )
        assert response.status_code == 302
        setup = SectionExamSetup.objects.get(section=section)
        assert setup.seconds_per_question == 40
        assert set(setup.subjects.values_list("pk", flat=True)) == {s1.pk, s2.pk}


@pytest.mark.django_db
class TestSectionHeatmapAndFeedback:
    def test_section_heatmap_and_feedback_ok(
        self, client, professor, bsed_program, year_level, academic_year
    ):
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="7M",
            academic_year=academic_year,
            max_students=40,
        )
        client.force_login(professor)
        heat = client.get(
            reverse(
                "analytics_professor:section_heatmap",
                kwargs={"section_pk": section.pk},
            )
        )
        assert heat.status_code == 200
        fb = client.get(
            reverse(
                "analytics_professor:section_feedback",
                kwargs={"section_pk": section.pk},
            )
        )
        assert fb.status_code == 200


@pytest.mark.django_db
class TestStudentMultiSelectSetup:
    def test_setup_page_includes_multi_select(
        self, client, student, mcq_question, bsed_program, subject
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        # Need enough subjects with questions for eligibility display
        for i in range(2):
            s = Subject.objects.create(
                program=bsed_program,
                code=f"MS-{i}",
                name=f"MS {i}",
                year_level=subject.year_level,
                semester=1,
            )
            t = Topic.objects.create(subject=s, name=f"T{i}")
            q = Question.objects.create(
                topic=t,
                difficulty=Question.Difficulty.EASY,
                question_type=Question.QuestionType.MCQ,
                stem=f"Q{i}",
                status=Question.Status.APPROVED,
            )
            QuestionChoice.objects.create(question=q, label="A", text="1", is_correct=True)

        client.force_login(student)
        response = client.get(reverse("reviews:setup"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "data-multi-select" in content
        assert "id_setup_subjects" in content

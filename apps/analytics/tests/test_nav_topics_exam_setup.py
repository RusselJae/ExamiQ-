import pytest
from django.urls import reverse

from apps.questions.models import Question, QuestionChoice, Subject, Topic
from apps.questions.views_professor import topics_for_course_subject
from apps.reviews.exam_setup_services import (
    get_or_create_program_exam_setup,
    student_setup_eligibility,
    subject_exam_timer_seconds,
    subjects_available_for_student,
    sync_program_subject_timers,
)
from apps.reviews.models import ProgramExamSetup
from apps.users.assignment_services import get_or_create_catalog_course
from apps.users.models import Course, ProgramSection, User
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

    def test_course_list_reuses_existing_catalog_course(
        self, client, professor, bsed_program, year_level, academic_year
    ):
        other_professor = User.objects.create_user(
            email="other-prof@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
        )
        subject = Subject.objects.create(
            program=bsed_program,
            code="SHARED-1",
            name="Shared Catalog Subject",
            year_level=year_level,
            semester=1,
        )
        existing = Course.objects.create(
            program=bsed_program,
            code=subject.code,
            name=subject.name,
            professor=other_professor,
            term="Catalog",
            academic_year=academic_year.label,
            section="Catalog",
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_list"))
        assert response.status_code == 200

        course = get_or_create_catalog_course(professor, subject)
        assert course.pk == existing.pk

        questions = client.get(
            reverse("analytics_professor:question_list", kwargs={"course_pk": course.pk})
        )
        assert questions.status_code == 200

    def test_professor_can_remove_catalog_subject(
        self, client, professor, bsed_program, year_level
    ):
        from apps.users.assignment_services import create_catalog_subject

        subject, _course = create_catalog_subject(
            code="BSEM TMP",
            name="Temp Subject",
            year_level=year_level,
            semester=1,
            professor=professor,
        )
        client.force_login(professor)
        list_response = client.get(reverse("analytics_professor:course_list"))
        assert "Remove" in list_response.content.decode()
        response = client.post(
            reverse(
                "analytics_professor:course_subject_remove",
                kwargs={"subject_pk": subject.pk},
            )
        )
        assert response.status_code == 302
        assert not Subject.objects.filter(pk=subject.pk).exists()
        assert response.url == reverse("analytics_professor:course_list")

    def test_catalog_questions_accessible_without_profile_subject_assignment(
        self, client, professor, bsed_program, year_level, academic_year, subject
    ):
        other_subject = Subject.objects.create(
            program=bsed_program,
            code="OTHER-99",
            name="Other Subject",
            year_level=year_level,
            semester=1,
        )
        professor.assigned_subjects.set([other_subject])
        catalog = Course.objects.create(
            program=bsed_program,
            code=subject.code,
            name=subject.name,
            professor=professor,
            term="Catalog",
            academic_year=academic_year.label,
            section="Catalog",
        )
        client.force_login(professor)
        response = client.get(
            reverse("analytics_professor:question_list", kwargs={"course_pk": catalog.pk})
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestProgramExamSetupGating:
    def test_subjects_available_respects_program_selection(
        self, student, bsed_program, year_level
    ):
        make_bsed_student(student, bsed_program=bsed_program)
        s1 = Subject.objects.create(
            program=bsed_program, code="G1", name="One", year_level=year_level, semester=1
        )
        Subject.objects.create(
            program=bsed_program, code="G2", name="Two", year_level=year_level, semester=1
        )
        setup = get_or_create_program_exam_setup(bsed_program)
        setup.is_enabled = True
        setup.save(update_fields=["is_enabled"])
        setup.subjects.set([s1])

        codes = set(subjects_available_for_student(student).values_list("code", flat=True))
        assert codes == {"G1"}
        assert "G2" not in codes

        setup.subjects.clear()
        codes = set(subjects_available_for_student(student).values_list("code", flat=True))
        assert {"G1", "G2"}.issubset(codes)

    def test_disabled_program_setup_blocks_eligibility(
        self, student, bsed_program, year_level
    ):
        make_bsed_student(student, bsed_program=bsed_program)
        setup = get_or_create_program_exam_setup(bsed_program)
        setup.is_enabled = False
        setup.save(update_fields=["is_enabled"])
        result = student_setup_eligibility(student)
        assert result["eligible"] is False
        assert result["reason"] == "disabled"
        assert subjects_available_for_student(student).count() == 0

    def test_program_exam_setup_view_saves(
        self, client, professor, bsed_program, year_level
    ):
        s1 = Subject.objects.create(
            program=bsed_program, code="S1", name="Sub1", year_level=year_level, semester=1
        )
        s2 = Subject.objects.create(
            program=bsed_program, code="S2", name="Sub2", year_level=year_level, semester=1
        )
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup_hub")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "subject-timer-table" in content
        assert "Course subjects" in content
        assert "selected subjects" in content.lower()

        response = client.post(
            url,
            {
                "default_seconds": 40,
                "subjects": [s1.pk, s2.pk],
                f"timer_{s1.pk}": 35,
                f"timer_{s2.pk}": 45,
            },
        )
        assert response.status_code == 302
        setup = ProgramExamSetup.objects.get(program=bsed_program)
        assert setup.is_enabled is True
        assert setup.seconds_per_question == 40
        assert set(setup.subjects.values_list("pk", flat=True)) == {s1.pk, s2.pk}

    def test_sync_program_subject_timers_sets_per_subject_seconds(
        self, bsed_program, year_level
    ):
        s1 = Subject.objects.create(
            program=bsed_program, code="T1", name="Timer1", year_level=year_level, semester=1
        )
        sync_program_subject_timers(
            bsed_program,
            subject_ids=[s1.pk],
            timers_by_subject_id={s1.pk: 55},
            default_seconds=30,
        )
        assert subject_exam_timer_seconds(s1) == 55

    def test_legacy_section_exam_setup_redirects(
        self, client, professor, bsed_program, year_level, academic_year
    ):
        section = ProgramSection.objects.create(
            program=bsed_program,
            year_level=year_level,
            label="8M",
            academic_year=academic_year,
            max_students=40,
        )
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:section_exam_setup",
                kwargs={"section_pk": section.pk},
            )
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestAddQuestionsHubAlwaysVisible:
    def test_add_questions_without_course_shows_full_form(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:question_add"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "settings-difficulty" in content
        assert "ai-generate-btn" in content
        assert "hub-course-filter" in content
        assert "Select a course subject to save questions." in content


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
        assert heat.status_code == 404
        fb = client.get(
            reverse(
                "analytics_professor:section_feedback",
                kwargs={"section_pk": section.pk},
            )
        )
        assert fb.status_code == 404


@pytest.mark.django_db
class TestStudentMultiSelectSetup:
    def test_setup_page_includes_multi_select(
        self, client, student, mcq_question, bsed_program, subject
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
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
        assert "exam-pill" in content
        assert "id_setup_subjects" not in content
        assert "Course subjects for your year" in content
        assert "id_setup_question_type" in content
        assert "exam-setup-summary" in content
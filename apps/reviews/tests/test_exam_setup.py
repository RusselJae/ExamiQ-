import pytest
from django.urls import reverse

from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.reviews.models import ExamSetup


@pytest.mark.django_db
class TestExamSetupViews:
    def test_professor_can_edit_exam_setup(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "Exam Setup" in response.content.decode()

    def test_exam_setup_auto_created_with_assignment(self, teaching_assignment):
        setup = get_or_create_exam_setup(teaching_assignment.course)
        assert setup.is_enabled is True
        assert setup.allowed_difficulties

    def test_professor_can_disable_exam_setup(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        setup = get_or_create_exam_setup(course)
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.post(
            url,
            {
                "is_enabled": "",
                "seconds_per_question": 40,
                "allowed_difficulties": setup.effective_difficulties(),
            },
        )
        assert response.status_code == 302
        setup.refresh_from_db()
        assert setup.is_enabled is False
        assert setup.seconds_per_question == 40

    def test_student_session_uses_exam_setup_timing(
        self, client, student, topic, mcq_question, bsed_program, course
    ):
        from apps.reviews.models import ReviewSession
        from conftest import make_bsed_student

        question, _ = mcq_question
        make_bsed_student(
            student, subject=topic.subject, course=course, bsed_program=bsed_program
        )
        topic.subject.code = course.code
        topic.subject.save(update_fields=["code"])

        setup = get_or_create_exam_setup(course)
        setup.seconds_per_question = 45
        setup.save(update_fields=["seconds_per_question"])

        client.force_login(student)
        from apps.questions.models import Question as QModel, QuestionChoice, Subject, Topic

        subjects = []
        for i in range(3):
            subj = Subject.objects.create(
                program=bsed_program,
                code=f"TIMING-{i}",
                name=f"Exam Subj {i}",
                year_level=topic.subject.year_level,
                semester=1,
            )
            top = Topic.objects.create(subject=subj, name=f"Timing T{i}")
            q = QModel.objects.create(
                topic=top,
                difficulty=question.difficulty,
                question_type=QModel.QuestionType.MCQ,
                stem=f"Timing Q {i}",
                status=QModel.Status.APPROVED,
            )
            QuestionChoice.objects.create(question=q, label="A", text="1", is_correct=True)
            QuestionChoice.objects.create(question=q, label="B", text="2", is_correct=False)
            subjects.append(subj)

        # Point faculty course code at first subject so exam timing resolves
        course.code = subjects[0].code
        course.save(update_fields=["code"])

        from apps.reviews.exam_setup_services import get_or_create_program_exam_setup

        program_setup = get_or_create_program_exam_setup(bsed_program)
        program_setup.subjects.set(subjects)

        response = client.post(
            reverse("reviews:setup"),
            {
                "difficulty": question.difficulty,
                "question_type": [QModel.QuestionType.MCQ],
            },
        )
        assert response.status_code == 302
        session = ReviewSession.objects.filter(student=student).latest("pk")
        assert session.seconds_per_question == 45

    def test_other_professor_cannot_access_exam_setup(
        self, client, professor, chairperson, program, teaching_assignment
    ):
        other = chairperson
        course = teaching_assignment.course
        client.force_login(other)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        assert response.status_code in (403, 404)

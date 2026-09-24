import pytest
from django.urls import reverse

from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.reviews.models import ExamSetup


@pytest.mark.django_db
class TestExamSetupViews:
    def test_professor_exam_setup_redirects(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        assert response.status_code == 302

    def test_exam_setup_auto_created_with_assignment(self, teaching_assignment):
        setup = get_or_create_exam_setup(teaching_assignment.course)
        assert setup.is_enabled is True
        assert setup.allowed_difficulties

    def test_student_session_uses_selected_timer(
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

        response = client.post(
            reverse("reviews:setup"),
            {
                "difficulty": question.difficulty,
                "question_type": [QModel.QuestionType.MCQ],
                "seconds_per_question": 55,
                "year_subjects": [s.pk for s in subjects],
            },
        )
        assert response.status_code == 302, response.content.decode()[:500]
        session = ReviewSession.objects.filter(student=student).latest("pk")
        assert session.seconds_per_question == 55

    def test_student_session_allows_no_timer(
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

        client.force_login(student)
        from apps.questions.models import Question as QModel, QuestionChoice, Subject, Topic

        subjects = []
        for i in range(3):
            subj = Subject.objects.create(
                program=bsed_program,
                code=f"NOTIME-{i}",
                name=f"No Timer Subj {i}",
                year_level=topic.subject.year_level,
                semester=1,
            )
            top = Topic.objects.create(subject=subj, name=f"NoTimer T{i}")
            q = QModel.objects.create(
                topic=top,
                difficulty=question.difficulty,
                question_type=QModel.QuestionType.MCQ,
                stem=f"NoTimer Q {i}",
                status=QModel.Status.APPROVED,
            )
            QuestionChoice.objects.create(question=q, label="A", text="1", is_correct=True)
            QuestionChoice.objects.create(question=q, label="B", text="2", is_correct=False)
            subjects.append(subj)

        response = client.post(
            reverse("reviews:setup"),
            {
                "difficulty": question.difficulty,
                "question_type": [QModel.QuestionType.MCQ],
                "seconds_per_question": 0,
                "year_subjects": [s.pk for s in subjects],
            },
        )
        assert response.status_code == 302, response.content.decode()[:500]
        session = ReviewSession.objects.filter(student=student).latest("pk")
        assert session.seconds_per_question == 0

    def test_other_professor_cannot_access_exam_setup(
        self, client, professor, chairperson, program, teaching_assignment
    ):
        other = chairperson
        course = teaching_assignment.course
        client.force_login(other)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        assert response.status_code in (302, 403, 404)

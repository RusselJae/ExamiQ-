"""Student role test cases — Confidence-Based Review module.

Maps to the manual test-case table ``docs/role-test-cases.md`` (Appendix A.1),
rows TC-S03 to TC-S05:

* TC-S03 Review Setup & Start Exam
* TC-S04 Submit Answer (confidence capture + automatic mistake logging)
* TC-S05 Session Summary

Each test asserts the behaviour promised in the "System Response" column and
the guard described in the "Actual Errors" column.
"""

import pytest
from django.urls import reverse

from apps.analytics.models import MistakeRecord
from apps.questions.models import Question
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.services import start_review_session


@pytest.mark.django_db
class TestStudentReviewSetup:
    """TC-S03 — Review setup and start of a timed exam."""

    def test_start_exam_creates_timed_session_and_redirects(
        self, client, bsed_student, bsed_mcq_question
    ):
        question, _ = bsed_mcq_question
        client.force_login(bsed_student)

        response = client.post(
            reverse("reviews:setup"),
            {
                "difficulty": Question.Difficulty.EASY,
                "question_type": [Question.QuestionType.MCQ],
                "seconds_per_question": 30,
                "questions_per_subject": 1,
                "year_subjects": [question.topic.subject_id],
            },
        )

        assert response.status_code == 302
        session = ReviewSession.objects.filter(student=bsed_student).latest("pk")
        assert session.mode == ReviewSession.Mode.TIMED_EXAM
        assert session.seconds_per_question == 30
        assert session.status == ReviewSession.Status.ACTIVE
        assert response.url == reverse("reviews:session", kwargs={"pk": session.pk})

    def test_setup_without_selected_subject_is_rejected(
        self, client, bsed_student, bsed_mcq_question
    ):
        """Actual error: no course subject ticked."""
        client.force_login(bsed_student)

        response = client.post(
            reverse("reviews:setup"),
            {
                "difficulty": Question.Difficulty.EASY,
                "question_type": [Question.QuestionType.MCQ],
                "seconds_per_question": 30,
                "year_subjects": [],
            },
        )

        assert response.status_code == 200
        assert (
            "Select at least one course subject to start an exam."
            in response.content.decode()
        )
        assert not ReviewSession.objects.filter(student=bsed_student).exists()

    def test_setup_rejects_timer_outside_allowed_range(
        self, client, bsed_student, bsed_mcq_question
    ):
        """Actual error: timer below the 10 second floor."""
        question, _ = bsed_mcq_question
        client.force_login(bsed_student)

        response = client.post(
            reverse("reviews:setup"),
            {
                "difficulty": Question.Difficulty.EASY,
                "question_type": [Question.QuestionType.MCQ],
                "seconds_per_question": 5,
                "year_subjects": [question.topic.subject_id],
            },
        )

        assert response.status_code == 200
        assert (
            "Timer must be 0 (no timer) or between 10 and 120 seconds."
            in response.content.decode()
        )
        assert not ReviewSession.objects.filter(student=bsed_student).exists()

    def test_student_without_year_level_cannot_start_exam(
        self, client, bsed_student, bsed_mcq_question
    ):
        """Actual error: incomplete profile (no year level)."""
        bsed_student.year_level = None
        bsed_student.save(update_fields=["year_level"])
        client.force_login(bsed_student)

        response = client.get(reverse("reviews:setup"))

        assert response.status_code == 200
        assert "Your year level is not set." in response.content.decode()


@pytest.mark.django_db
class TestStudentSubmitAnswer:
    """TC-S04 — Answer submission, confidence capture and mistake logging."""

    @pytest.fixture
    def session(self, bsed_student, bsed_mcq_question):
        question, _ = bsed_mcq_question
        return start_review_session(
            student=bsed_student,
            topic=question.topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=30,
        )

    def test_correct_answer_is_graded_and_confidence_stored(
        self, client, bsed_student, bsed_mcq_question, session
    ):
        question, correct = bsed_mcq_question
        client.force_login(bsed_student)

        response = client.post(
            reverse(
                "reviews:submit_answer",
                kwargs={"pk": session.pk, "question_id": question.pk},
            ),
            {
                "selected_choice": correct.pk,
                "confidence": "5",
                "time_spent_seconds": "8",
                "timed_out": "false",
            },
        )

        assert response.status_code == 200
        answer = session.answers.get()
        assert answer.is_correct is True
        assert answer.confidence == 5
        assert not MistakeRecord.objects.filter(student=bsed_student).exists()

    def test_wrong_answer_is_logged_as_a_mistake(
        self, client, bsed_student, bsed_mcq_question, session
    ):
        question, _ = bsed_mcq_question
        wrong = question.choices.filter(is_correct=False).first()
        client.force_login(bsed_student)

        response = client.post(
            reverse(
                "reviews:submit_answer",
                kwargs={"pk": session.pk, "question_id": question.pk},
            ),
            {
                "selected_choice": wrong.pk,
                "confidence": "1",
                "time_spent_seconds": "12",
                "timed_out": "false",
            },
        )

        assert response.status_code == 200
        answer = session.answers.get()
        assert answer.is_correct is False
        assert answer.confidence == 1
        assert MistakeRecord.objects.filter(
            student=bsed_student, question=question
        ).exists()

    def test_answer_without_confidence_is_rejected(
        self, client, bsed_student, bsed_mcq_question, session
    ):
        """Actual error: confidence not captured."""
        question, correct = bsed_mcq_question
        client.force_login(bsed_student)

        response = client.post(
            reverse(
                "reviews:submit_answer",
                kwargs={"pk": session.pk, "question_id": question.pk},
            ),
            {
                "selected_choice": correct.pk,
                "confidence": "",
                "time_spent_seconds": "4",
                "timed_out": "false",
            },
        )

        assert response.status_code == 200
        assert (
            "Please select how sure you were."
            in response.context["form"].errors.as_text()
        )
        assert (
            "Please select an answer and how sure you were."
            in response.content.decode()
        )
        assert not Answer.objects.filter(session=session).exists()

    def test_answer_without_response_is_rejected(
        self, client, bsed_student, bsed_mcq_question, session
    ):
        """Actual error: no answer selected."""
        question, _ = bsed_mcq_question
        client.force_login(bsed_student)

        response = client.post(
            reverse(
                "reviews:submit_answer",
                kwargs={"pk": session.pk, "question_id": question.pk},
            ),
            {
                "confidence": "5",
                "time_spent_seconds": "4",
                "timed_out": "false",
            },
        )

        assert response.status_code == 200
        assert "Please select an answer." in response.context["form"].errors.as_text()
        assert (
            "Please select an answer and how sure you were."
            in response.content.decode()
        )
        assert not Answer.objects.filter(session=session).exists()

    def test_student_cannot_answer_in_another_students_session(
        self, client, student, bsed_student, bsed_mcq_question, session
    ):
        """Actual error: session belongs to somebody else."""
        question, correct = bsed_mcq_question
        client.force_login(student)

        response = client.post(
            reverse(
                "reviews:submit_answer",
                kwargs={"pk": session.pk, "question_id": question.pk},
            ),
            {
                "selected_choice": correct.pk,
                "confidence": "5",
                "time_spent_seconds": "4",
                "timed_out": "false",
            },
        )

        assert response.status_code == 404
        assert not Answer.objects.filter(session=session).exists()


@pytest.mark.django_db
class TestStudentSessionSummary:
    """TC-S05 — Session summary and recommendations."""

    @pytest.fixture
    def session(self, bsed_student, bsed_mcq_question):
        question, _ = bsed_mcq_question
        return start_review_session(
            student=bsed_student,
            topic=question.topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=30,
        )

    def test_summary_renders_for_own_session(self, client, bsed_student, session):
        client.force_login(bsed_student)

        response = client.get(reverse("reviews:summary", kwargs={"pk": session.pk}))

        assert response.status_code == 200
        assert "session_summary" in response.context

    def test_summary_is_hidden_from_other_students(
        self, client, student, bsed_student, session
    ):
        """Actual error: session belongs to somebody else."""
        client.force_login(student)

        response = client.get(reverse("reviews:summary", kwargs={"pk": session.pk}))

        assert response.status_code == 404

    def test_session_page_is_hidden_from_other_students(
        self, client, student, bsed_student, session
    ):
        """Actual error: session belongs to somebody else."""
        client.force_login(student)

        response = client.get(reverse("reviews:session", kwargs={"pk": session.pk}))

        assert response.status_code == 404

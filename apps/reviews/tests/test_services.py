import pytest

from apps.analytics.services import log_mistake
from apps.reviews.models import ReviewSession
from apps.reviews.services import SessionExpiredError, start_review_session, submit_answer
from apps.users.models import Course


@pytest.mark.django_db
class TestReviewServices:
    def test_submit_answer_creates_mistake_on_wrong(self, student, mcq_question, program, topic):
        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="T101",
            name="Test",
            term="1st Sem",
            academic_year="2026",
            section="A",
        )

        session = start_review_session(student, topic, "easy", 15, course=course)
        wrong = question.choices.filter(is_correct=False).first()
        answer = submit_answer(
            session=session,
            question=question,
            confidence=3,
            selected_choice=wrong,
        )
        assert answer.is_correct is False
        assert hasattr(answer, "mistake_record")
        assert answer.mistake_record.ai_feedback == ""

    def test_generate_mistake_feedback_persists_text(self, student, mcq_question, program, topic):
        from apps.analytics.services import generate_mistake_feedback

        question, _ = mcq_question
        session = start_review_session(student, topic, "easy", 15)
        wrong = question.choices.filter(is_correct=False).first()
        answer = submit_answer(
            session=session,
            question=question,
            confidence=3,
            selected_choice=wrong,
        )
        record = answer.mistake_record
        text = generate_mistake_feedback(record)
        record.refresh_from_db()
        assert text
        assert record.ai_feedback == text

    def test_session_expired_rejects_submission(self, student, mcq_question):
        question, correct = mcq_question
        session = start_review_session(
            student,
            question.topic,
            "easy",
            15,
            mode=ReviewSession.Mode.PRACTICE_REVIEW,
        )
        session.started_at = session.started_at.replace(year=2020)
        session.save()

        with pytest.raises(SessionExpiredError):
            submit_answer(session=session, question=question, confidence=4, selected_choice=correct)

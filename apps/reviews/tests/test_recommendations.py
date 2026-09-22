import pytest
from django.utils import timezone

from apps.analytics.models import MistakeRecord
from apps.questions.models import Question, QuestionChoice
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.recommendations import build_session_summary, get_review_recommendations
from apps.reviews.services import complete_session, start_review_session


@pytest.mark.django_db
class TestRecommendations:
    def test_build_session_summary_includes_calibration(self, student, course, topic):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            course=course,
        )
        q = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Test?",
            status=Question.Status.APPROVED,
        )
        correct = QuestionChoice.objects.create(question=q, label="A", text="yes", is_correct=True)
        Answer.objects.create(
            session=session,
            question=q,
            selected_choice=correct,
            confidence=5,
            is_correct=True,
        )
        complete_session(session)

        summary = build_session_summary(session)
        assert summary["total_questions"] == 1
        assert summary["accuracy"] == 100.0
        assert "calibration_matrix" in summary
        assert summary["narrative"]
        assert "avg_time_confidence_label" in summary
        assert "avg_confidence_label" in summary
        assert summary["avg_confidence_label"] == "Sure"

    def test_misconception_triggers_high_priority_recommendation(self, student, course, topic):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            course=course,
        )
        q = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Wrong?",
            status=Question.Status.APPROVED,
        )
        wrong = QuestionChoice.objects.create(question=q, label="B", text="no", is_correct=False)
        answer = Answer.objects.create(
            session=session,
            question=q,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        MistakeRecord.objects.create(
            student=student,
            question=q,
            topic=topic,
            answer=answer,
        )
        complete_session(session)

        recs = get_review_recommendations(student, limit=5)
        assert recs
        assert recs[0]["topic"].pk == topic.pk
        assert recs[0]["priority"] == "high"

import pytest

from apps.analytics.models import MistakeRecord
from apps.analytics.services import get_intervention_list
from apps.questions.models import Question, QuestionChoice
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.services import complete_session, start_review_session


@pytest.mark.django_db
class TestInterventionList:
    def test_flags_overconfident_student(self, student, course, topic):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            course=course,
        )
        for _ in range(2):
            q = Question.objects.create(
                topic=topic,
                difficulty=Question.Difficulty.EASY,
                question_type=Question.QuestionType.MCQ,
                stem=f"Q {_}?",
                status=Question.Status.APPROVED,
            )
            wrong = QuestionChoice.objects.create(
                question=q, label="B", text="no", is_correct=False
            )
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

        rows = get_intervention_list(course)
        assert len(rows) == 1
        assert "overconfident" in rows[0]["flags"]

    def test_empty_when_all_on_track(self, course):
        assert get_intervention_list(course) == []

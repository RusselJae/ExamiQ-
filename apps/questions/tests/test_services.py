from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.analytics.models import MistakeRecord
from apps.questions.models import Question, QuestionChoice
from apps.questions.services import get_adaptive_questions_for_session, grade_answer
from apps.reviews.models import Answer, ReviewSession


@pytest.mark.django_db
class TestGradeAnswer:
    def test_mcq_correct(self, mcq_question):
        question, correct_choice = mcq_question
        is_correct, ctx = grade_answer(question, selected_choice=correct_choice)
        assert is_correct is True

    def test_mcq_incorrect(self, mcq_question):
        question, _ = mcq_question
        wrong = question.choices.filter(is_correct=False).first()
        is_correct, _ = grade_answer(question, selected_choice=wrong)
        assert is_correct is False

    def test_numeric_correct(self, numeric_question):
        is_correct, _ = grade_answer(numeric_question, submitted_value="3")
        assert is_correct is True

    def test_numeric_within_tolerance(self, numeric_question):
        is_correct, _ = grade_answer(numeric_question, submitted_value="3.005")
        assert is_correct is True

    def test_numeric_incorrect(self, numeric_question):
        is_correct, _ = grade_answer(numeric_question, submitted_value="5")
        assert is_correct is False


@pytest.mark.django_db
class TestAdaptiveQuestions:
    def test_prioritizes_mistake_topic_questions(self, student, topic):
        q_weak = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Weak area?",
            status=Question.Status.APPROVED,
        )
        QuestionChoice.objects.create(question=q_weak, label="A", text="x", is_correct=True)
        q_other = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Other?",
            status=Question.Status.APPROVED,
        )
        QuestionChoice.objects.create(question=q_other, label="A", text="y", is_correct=True)
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            duration_minutes=15,
        )
        wrong = QuestionChoice.objects.create(question=q_weak, label="B", text="z", is_correct=False)
        answer = Answer.objects.create(
            session=session,
            question=q_weak,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        MistakeRecord.objects.create(
            student=student,
            question=q_weak,
            topic=topic,
            answer=answer,
        )

        picks = []
        with patch("random.random", return_value=0.5):
            for _ in range(50):
                result = get_adaptive_questions_for_session(
                    student, topic, Question.Difficulty.EASY, count=1
                ).first()
                if result:
                    picks.append(result.pk)

        assert picks.count(q_weak.pk) > picks.count(q_other.pk)

    def test_prioritizes_high_confidence_wrong_repeats(self, student, topic):
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            duration_minutes=15,
        )
        q_repeat = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Repeat?",
            status=Question.Status.APPROVED,
        )
        wrong = QuestionChoice.objects.create(question=q_repeat, label="B", text="no", is_correct=False)
        Answer.objects.create(
            session=session,
            question=q_repeat,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        q_new = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="New?",
            status=Question.Status.APPROVED,
        )
        QuestionChoice.objects.create(question=q_new, label="A", text="yes", is_correct=True)

        picks = []
        with patch("random.random", return_value=0.5):
            for _ in range(50):
                result = get_adaptive_questions_for_session(
                    student, topic, Question.Difficulty.EASY, count=1
                ).first()
                if result:
                    picks.append(result.pk)

        assert picks.count(q_repeat.pk) >= picks.count(q_new.pk)
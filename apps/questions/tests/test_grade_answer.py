"""Tests for grading Multiple Choice and new text question types."""

import pytest

from apps.questions.models import Question, QuestionChoice
from apps.questions.services import grade_answer


@pytest.mark.django_db
class TestGradeAnswerTypes:
    def test_true_false_accepts_aliases(self, topic):
        question = Question.objects.create(
            topic=topic,
            stem="π is irrational.",
            question_type=Question.QuestionType.TRUE_FALSE,
            expected_answer="True",
            difficulty=Question.Difficulty.EASY,
        )
        ok, ctx = grade_answer(question, submitted_value="yes")
        assert ok is True
        assert ctx["expected_answer"] == "True"

        ok, _ = grade_answer(question, submitted_value="False")
        assert ok is False

    def test_identification_is_case_insensitive(self, topic):
        question = Question.objects.create(
            topic=topic,
            stem="Name the derivative of x².",
            question_type=Question.QuestionType.IDENTIFICATION,
            expected_answer="2x",
            difficulty=Question.Difficulty.MEDIUM,
        )
        ok, _ = grade_answer(question, submitted_value=" 2X ")
        assert ok is True
        ok, _ = grade_answer(question, submitted_value="x2")
        assert ok is False

    def test_identification_ignores_capitalization_in_phrases(self, topic):
        question = Question.objects.create(
            topic=topic,
            stem="What property allows changing order in addition?",
            question_type=Question.QuestionType.IDENTIFICATION,
            expected_answer="Commutative Property",
            difficulty=Question.Difficulty.EASY,
        )
        ok, _ = grade_answer(question, submitted_value="commutative property")
        assert ok is True
        ok, _ = grade_answer(question, submitted_value="COMMUTATIVE PROPERTY")
        assert ok is True

    def test_enumeration_requires_all_items(self, topic):
        question = Question.objects.create(
            topic=topic,
            stem="List the first three primes.",
            question_type=Question.QuestionType.ENUMERATION,
            expected_answer="2\n3\n5",
            difficulty=Question.Difficulty.EASY,
        )
        ok, _ = grade_answer(question, submitted_value="5\n2\n3")
        assert ok is True
        ok, _ = grade_answer(question, submitted_value="2\n3")
        assert ok is False

    def test_mcq_still_uses_choices(self, topic):
        question = Question.objects.create(
            topic=topic,
            stem="2+2?",
            question_type=Question.QuestionType.MCQ,
            difficulty=Question.Difficulty.EASY,
        )
        correct = QuestionChoice.objects.create(
            question=question, label="A", text="4", is_correct=True
        )
        QuestionChoice.objects.create(
            question=question, label="B", text="5", is_correct=False
        )
        ok, _ = grade_answer(question, selected_choice=correct)
        assert ok is True

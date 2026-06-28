import pytest

from apps.questions.models import Question
from apps.questions.services import create_question, find_duplicate_question, normalize_stem


@pytest.mark.django_db
class TestDuplicateQuestionDetection:
    def test_normalize_stem_collapses_whitespace(self):
        assert normalize_stem("  What   is  2+2?  ") == "what is 2+2?"

    def test_find_duplicate_question_within_topic(self, topic):
        create_question(
            {
                "topic": topic,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "What is 2+2?",
                "is_active": True,
                "status": Question.Status.APPROVED,
            },
            [{"label": "A", "text": "4", "is_correct": True}],
            [],
        )
        duplicate = find_duplicate_question(topic.pk, "  what is  2+2? ")
        assert duplicate is not None

    def test_no_duplicate_for_different_stem(self, topic):
        create_question(
            {
                "topic": topic,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "What is 2+2?",
                "is_active": True,
                "status": Question.Status.APPROVED,
            },
            [{"label": "A", "text": "4", "is_correct": True}],
            [],
        )
        assert find_duplicate_question(topic.pk, "What is 3+3?") is None

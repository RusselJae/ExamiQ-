import pytest

from apps.questions.validation import validate_question_structure


@pytest.mark.django_db
class TestQuestionStructureValidation:
    def test_requires_four_distinct_choices(self):
        result = validate_question_structure(
            "What is 2+2?",
            [
                {"label": "A", "text": "4", "is_correct": True},
                {"label": "B", "text": "5", "is_correct": False},
            ],
            "A",
        )
        assert result["is_valid"] is False
        assert any("four" in e.lower() for e in result["errors"])

    def test_rejects_duplicate_choice_text(self):
        result = validate_question_structure(
            "Pick one",
            [
                {"label": "A", "text": "same", "is_correct": True},
                {"label": "B", "text": "same", "is_correct": False},
                {"label": "C", "text": "other", "is_correct": False},
                {"label": "D", "text": "another", "is_correct": False},
            ],
            "A",
        )
        assert result["is_valid"] is False

    def test_valid_mcq_passes(self):
        result = validate_question_structure(
            "What is 2+2?",
            [
                {"label": "A", "text": "4", "is_correct": True},
                {"label": "B", "text": "5", "is_correct": False},
                {"label": "C", "text": "6", "is_correct": False},
                {"label": "D", "text": "7", "is_correct": False},
            ],
            "A",
        )
        assert result["is_valid"] is True

import pytest

from apps.questions.validation import (
    check_duplicate_stem,
    validate_question_for_submit,
    validate_question_structure,
)


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


@pytest.mark.django_db
class TestDuplicateValidation:
    def test_exact_duplicate_in_bank_fails(self, topic):
        from apps.questions.services import create_question
        from apps.questions.models import Question

        create_question(
            {
                "topic": topic,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "What is the identity matrix?",
                "concept_tag": "identity",
                "is_active": True,
                "status": Question.Status.APPROVED,
            },
            [
                {"label": "A", "text": "I", "is_correct": True},
                {"label": "B", "text": "0", "is_correct": False},
                {"label": "C", "text": "A", "is_correct": False},
                {"label": "D", "text": "B", "is_correct": False},
            ],
            [],
        )
        message = check_duplicate_stem(topic.pk, "  What is the identity matrix? ")
        assert message is not None
        assert "question bank" in message

    def test_peer_duplicate_fails(self, topic):
        message = check_duplicate_stem(
            topic.pk,
            "What is 2+2?",
            peer_stems=["What is 3+3?", "What is 2+2?"],
        )
        assert message is not None
        assert "row 2" in message

    def test_similar_but_not_exact_stem_passes_duplicate_check(self, topic):
        message = check_duplicate_stem(
            topic.pk,
            "What is 2+2?",
            peer_stems=["What is 3+3?"],
        )
        assert message is None

    def test_validate_for_submit_marks_duplicate_invalid(self, topic):
        result = validate_question_for_submit(
            "What is 2+2?",
            [
                {"label": "A", "text": "4", "is_correct": True},
                {"label": "B", "text": "5", "is_correct": False},
                {"label": "C", "text": "6", "is_correct": False},
                {"label": "D", "text": "7", "is_correct": False},
            ],
            topic,
            "easy",
            "A",
            ai_enabled=False,
            peer_stems=["What is 2+2?"],
        )
        assert result["is_valid"] is False
        assert "Duplicate" in result["feedback"]

    def test_off_subject_stem_rejected(self, topic, settings):
        settings.AI_ENABLED = False
        topic.subject.code = "GNED 03"
        topic.subject.name = "Mathematics in the Modern World"
        topic.subject.save(update_fields=["code", "name"])
        result = validate_question_for_submit(
            "What is love?",
            [
                {"label": "A", "text": "4", "is_correct": True},
                {"label": "B", "text": "5", "is_correct": False},
                {"label": "C", "text": "6", "is_correct": False},
                {"label": "D", "text": "7", "is_correct": False},
            ],
            topic,
            "easy",
            "A",
            ai_enabled=True,
        )
        assert result["is_valid"] is False
        assert "GNED 03" in result["feedback"]

    def test_off_subject_rejected_before_structure_errors(self, topic, settings):
        settings.AI_ENABLED = False
        topic.subject.code = "GNED 03"
        topic.subject.name = "Mathematics in the Modern World"
        topic.subject.save(update_fields=["code", "name"])
        result = validate_question_for_submit(
            "What is love?",
            [],
            topic,
            "easy",
            "A",
            ai_enabled=True,
            question_type="mcq",
        )
        assert result["is_valid"] is False
        assert "GNED 03" in result["feedback"] or "not look related" in result["feedback"].lower()
        assert "four choices" not in result["feedback"].lower()

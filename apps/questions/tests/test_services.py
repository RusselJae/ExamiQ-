import pytest

from apps.questions.models import Question
from apps.questions.services import (
    create_question,
    find_duplicate_question,
    generation_fit_meta,
    normalize_stem,
)


class TestGenerationFitMeta:
    def test_on_band_with_reasoning_is_good_fit(self):
        meta = generation_fit_meta(
            {"difficulty": "medium", "explanation_steps": ["a", "b"]},
            ["easy", "medium"],
        )
        assert meta["fit"] == "good"
        assert meta["flag"] == ""
        assert meta["reasoning_note"] == "2 steps"
        assert meta["can_regenerate_harder"] is False

    def test_single_step_is_flagged_as_shallow(self):
        meta = generation_fit_meta(
            {"difficulty": "medium", "explanation_steps": ["only"]},
            ["medium"],
        )
        assert meta["fit"] == "shallow"
        assert meta["reasoning_note"] == "1 step, no reasoning"
        assert meta["flag"] == "Rounds on Intermediate"
        assert meta["can_regenerate_harder"] is True
        assert meta["next_difficulty"] == "hard"

    def test_missing_steps_says_no_reasoning(self):
        meta = generation_fit_meta({"difficulty": "easy"}, ["easy"])
        assert meta["fit"] == "shallow"
        assert meta["reasoning_note"] == "No reasoning steps"
        assert meta["flag"] == "Rounds on Beginner"

    def test_beginner_draft_in_wide_mix_offers_harder_regeneration(self):
        meta = generation_fit_meta(
            {"difficulty": "easy", "explanation_steps": ["a"]},
            ["easy", "medium", "hard"],
        )
        assert meta["fit"] == "shallow"
        assert meta["flag"] == "Rounds on Beginner"
        assert meta["can_regenerate_harder"] is True
        assert meta["next_difficulty"] == "medium"

    def test_top_band_cannot_regenerate_harder(self):
        meta = generation_fit_meta(
            {"difficulty": "hard", "explanation_steps": ["a", "b"]},
            ["easy"],
        )
        assert meta["fit"] == "off_band"
        assert meta["flag"] == "Above the requested mix"
        assert meta["can_regenerate_harder"] is False

    def test_unknown_difficulty_falls_back_to_first_requested_band(self):
        meta = generation_fit_meta(
            {"difficulty": "nonsense", "explanation_steps": ["a", "b"]},
            ["medium"],
        )
        assert meta["difficulty_code"] == "medium"
        assert meta["difficulty_label"] == "Intermediate"


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

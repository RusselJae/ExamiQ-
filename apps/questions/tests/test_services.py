import pytest

from apps.questions.models import Question
from apps.questions.services import (
    create_question,
    exclude_stem_from_generation,
    exclusion_set_for_topic,
    exclusion_stems_for_topic,
    find_duplicate_question,
    generation_fit_meta,
    normalize_stem,
    stem_fingerprint,
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


@pytest.mark.django_db
class TestStemExclusionRegistry:
    def test_exclude_stem_is_idempotent(self, topic):
        created_first = exclude_stem_from_generation(
            topic_id=topic.pk, stem="What is 2+2?"
        )
        created_second = exclude_stem_from_generation(
            topic_id=topic.pk, stem="  what is 2+2? "
        )
        assert created_first is True
        assert created_second is False
        from apps.questions.models import ExcludedQuestion

        assert ExcludedQuestion.objects.filter(topic=topic).count() == 1

    def test_whitespace_stem_is_ignored(self, topic):
        assert exclude_stem_from_generation(topic_id=topic.pk, stem="   ") is False
        assert exclusion_set_for_topic(topic.pk) == set()

    def test_exclusion_set_and_stems_round_trip(self, topic):
        exclude_stem_from_generation(topic_id=topic.pk, stem="First stem.")
        exclude_stem_from_generation(topic_id=topic.pk, stem="Second stem.")
        keys = exclusion_set_for_topic(topic.pk)
        assert len(keys) == 2
        assert all(len(key) == 64 for key in keys)

        stems = exclusion_stems_for_topic(topic_id=topic.pk)
        assert set(stems) == {"First stem.", "Second stem."}

    def test_stem_fingerprint_matches_registry(self, topic):
        exclude_stem_from_generation(topic_id=topic.pk, stem="What is 2+2?")
        fingerprint = stem_fingerprint(topic.pk, "  What   is 2+2? ")
        assert fingerprint in exclusion_set_for_topic(topic.pk)

    def test_truncation_applies_limit_and_length(self, topic):
        from apps.questions.models import ExcludedQuestion

        for i in range(45):
            ExcludedQuestion.objects.create(
                topic=topic,
                stem=f"Stem number {i} " + ("x" * 300),
                stem_key=f"{i:064x}",
            )
        stems = exclusion_stems_for_topic(topic_id=topic.pk)
        assert len(stems) == 40
        assert all(len(stem) <= 240 for stem in stems)
        # Newest first per Meta ordering.
        assert stems[0].startswith("Stem number 44")

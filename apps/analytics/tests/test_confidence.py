from apps.analytics.confidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    PACE_QUICK,
    PACE_SLOW,
    PACE_STEADY,
    PACE_UNANSWERED,
    avg_confidence_scale_label,
    confidence_from_time_spent,
    confidence_tier_key,
    confidence_to_scale_0_3,
    pace_from_answer,
)


class DummyAnswer:
    def __init__(
        self,
        *,
        selected_choice_id=None,
        numeric_response="",
        time_spent_seconds=5,
        is_correct=True,
        timed_out=False,
    ):
        self.selected_choice_id = selected_choice_id
        self.numeric_response = numeric_response
        self.time_spent_seconds = time_spent_seconds
        self.is_correct = is_correct
        self.timed_out = timed_out


class TestConfidenceFromTimeSpent:
    def test_default_30_second_scale(self):
        assert confidence_from_time_spent(5, 30) == CONFIDENCE_HIGH
        assert confidence_from_time_spent(15, 30) == CONFIDENCE_MEDIUM
        assert confidence_from_time_spent(25, 30) == CONFIDENCE_LOW

    def test_scales_with_longer_per_question_limit(self):
        assert confidence_from_time_spent(20, 60) == CONFIDENCE_HIGH
        assert confidence_from_time_spent(44, 60) == CONFIDENCE_MEDIUM
        assert confidence_from_time_spent(55, 60) == CONFIDENCE_LOW

    def test_confidence_tier_key(self):
        assert confidence_tier_key(None) == "none"
        assert confidence_tier_key(CONFIDENCE_LOW) == "low"
        assert confidence_tier_key(CONFIDENCE_MEDIUM) == "average"
        assert confidence_tier_key(CONFIDENCE_HIGH) == "high"

    def test_confidence_to_scale_0_3(self):
        assert confidence_to_scale_0_3(None) == 0
        assert confidence_to_scale_0_3(1) == 1
        assert confidence_to_scale_0_3(2) == 1
        assert confidence_to_scale_0_3(3) == 2
        assert confidence_to_scale_0_3(5) == 3

    def test_avg_confidence_scale_label(self):
        assert avg_confidence_scale_label([]) == "—"
        assert avg_confidence_scale_label([1, 1]) == "Guessing"
        assert avg_confidence_scale_label([3, 3]) == "Not sure"
        assert avg_confidence_scale_label([5, 5]) == "Sure"
        assert avg_confidence_scale_label([None, 5]) == "Not sure"

    def test_pace_from_answer_buckets(self):
        assert (
            pace_from_answer(DummyAnswer(selected_choice_id=1, time_spent_seconds=5))
            == PACE_QUICK
        )
        assert (
            pace_from_answer(DummyAnswer(selected_choice_id=1, time_spent_seconds=15))
            == PACE_STEADY
        )
        assert (
            pace_from_answer(DummyAnswer(selected_choice_id=1, time_spent_seconds=25))
            == PACE_SLOW
        )
        assert pace_from_answer(DummyAnswer(timed_out=True, is_correct=False)) == (
            PACE_UNANSWERED
        )

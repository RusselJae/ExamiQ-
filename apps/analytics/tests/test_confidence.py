import pytest

from apps.analytics.confidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    avg_confidence_scale_label,
    confidence_from_time_spent,
    confidence_tier_key,
    confidence_to_scale_0_3,
)


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
        assert avg_confidence_scale_label([1, 1]) == "Low"
        assert avg_confidence_scale_label([3, 3]) == "Average"
        assert avg_confidence_scale_label([5, 5]) == "High"
        assert avg_confidence_scale_label([None, 5]) == "Average"

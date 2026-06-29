import pytest

from apps.analytics.confidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    confidence_from_time_spent,
    confidence_tier_key,
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

"""Confidence-based answer classification for analytics."""

from django.db.models import Count, Q, QuerySet

CONFIDENCE_LOW = 1
CONFIDENCE_MEDIUM = 3
CONFIDENCE_HIGH = 5
VALID_CONFIDENCE_TIERS = {CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH}

HIGH_CONFIDENCE_MAX_SECONDS = 10
AVERAGE_CONFIDENCE_MAX_SECONDS = 22
CONFIDENCE_TIMER_CAP_SECONDS = 30

CLASSIFICATION_MASTERY = "mastery"
CLASSIFICATION_MISCONCEPTION = "misconception"
CLASSIFICATION_LUCKY_GUESS = "lucky_guess"
CLASSIFICATION_EXPECTED_GAP = "expected_gap"
CLASSIFICATION_UNCERTAIN = "uncertain"

CLASSIFICATION_LABELS = {
    CLASSIFICATION_MASTERY: "Mastery",
    CLASSIFICATION_MISCONCEPTION: "Misconception",
    CLASSIFICATION_LUCKY_GUESS: "Lucky guess",
    CLASSIFICATION_EXPECTED_GAP: "Expected gap",
    CLASSIFICATION_UNCERTAIN: "Uncertain",
}

CONFIDENCE_TIER_NONE = "none"
CONFIDENCE_TIER_LOW = "low"
CONFIDENCE_TIER_AVERAGE = "average"
CONFIDENCE_TIER_HIGH = "high"

CONFIDENCE_TIER_LABELS = {
    CONFIDENCE_TIER_NONE: "No",
    CONFIDENCE_TIER_LOW: "Low",
    CONFIDENCE_TIER_AVERAGE: "Average",
    CONFIDENCE_TIER_HIGH: "High",
}


def confidence_from_time_spent(seconds: int) -> int:
    """Map response time to confidence tier (high / average / low)."""
    capped = min(max(seconds, 0), CONFIDENCE_TIMER_CAP_SECONDS)
    if capped <= HIGH_CONFIDENCE_MAX_SECONDS:
        return CONFIDENCE_HIGH
    if capped <= AVERAGE_CONFIDENCE_MAX_SECONDS:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def classify_answer(confidence: int, is_correct: bool) -> str:
    """Classify an answer into a confidence×accuracy quadrant."""
    if confidence == CONFIDENCE_HIGH:
        return CLASSIFICATION_MASTERY if is_correct else CLASSIFICATION_MISCONCEPTION
    if confidence == CONFIDENCE_LOW:
        return CLASSIFICATION_LUCKY_GUESS if is_correct else CLASSIFICATION_EXPECTED_GAP
    return CLASSIFICATION_UNCERTAIN


def confidence_accuracy_matrix(answers_qs: QuerySet) -> dict[str, int]:
    """Return counts per classification quadrant."""
    matrix = {key: 0 for key in CLASSIFICATION_LABELS}
    for row in answers_qs.values("confidence", "is_correct"):
        matrix[classify_answer(row["confidence"], row["is_correct"])] += 1
    return matrix


def confidence_tier_matrix(answers_qs: QuerySet) -> dict[str, int]:
    """Return answer counts grouped by reported confidence tier."""
    matrix = {key: 0 for key in CONFIDENCE_TIER_LABELS}
    for row in answers_qs.values("confidence"):
        confidence = row["confidence"]
        if confidence is None:
            matrix[CONFIDENCE_TIER_NONE] += 1
        elif confidence == CONFIDENCE_LOW:
            matrix[CONFIDENCE_TIER_LOW] += 1
        elif confidence == CONFIDENCE_MEDIUM:
            matrix[CONFIDENCE_TIER_AVERAGE] += 1
        elif confidence == CONFIDENCE_HIGH:
            matrix[CONFIDENCE_TIER_HIGH] += 1
        else:
            matrix[CONFIDENCE_TIER_NONE] += 1
    return matrix


def misconception_topics(answers_qs: QuerySet, limit: int = 10) -> list[dict]:
    """Topics with the most high-confidence wrong answers."""
    return list(
        answers_qs.filter(confidence=CONFIDENCE_HIGH, is_correct=False)
        .values("question__topic__name", "question__topic_id")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:limit]
    )

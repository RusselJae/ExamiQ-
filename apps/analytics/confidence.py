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
    CONFIDENCE_TIER_NONE: "No Confidence",
    CONFIDENCE_TIER_LOW: "Low Confidence",
    CONFIDENCE_TIER_AVERAGE: "Average Confidence",
    CONFIDENCE_TIER_HIGH: "High Confidence",
}

CONFIDENCE_SCALE_0_3_LABELS = {
    0: "No Confidence",
    1: "Low",
    2: "Average",
    3: "High",
}


def confidence_to_scale_0_3(value) -> int:
    """Map stored 1–5 / null confidence onto chart scale 0–3."""
    if value is None:
        return 0
    try:
        confidence = int(value)
    except (TypeError, ValueError):
        return 0
    if confidence <= 0:
        return 0
    if confidence <= 2:
        return 1
    if confidence <= 4:
        return 2
    return 3


def avg_confidence_scale_label(confidence_values) -> str:
    """Average mapped 0–3 confidences into a short display label."""
    values = [confidence_to_scale_0_3(value) for value in confidence_values]
    if not values:
        return "—"
    average = round(sum(values) / len(values))
    return CONFIDENCE_SCALE_0_3_LABELS.get(max(0, min(3, average)), "—")


def confidence_from_time_spent(seconds: int, seconds_per_question: int = 30) -> int:
    """Map response time to confidence tier, scaled to the per-question limit."""
    cap = max(seconds_per_question, 1)
    capped = min(max(seconds, 0), cap)
    high_max = cap * HIGH_CONFIDENCE_MAX_SECONDS / CONFIDENCE_TIMER_CAP_SECONDS
    avg_max = cap * AVERAGE_CONFIDENCE_MAX_SECONDS / CONFIDENCE_TIMER_CAP_SECONDS
    if capped <= high_max:
        return CONFIDENCE_HIGH
    if capped <= avg_max:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def confidence_tier_key(confidence: int | None) -> str:
    """Map stored confidence value to tier key."""
    if confidence is None:
        return CONFIDENCE_TIER_NONE
    if confidence == CONFIDENCE_LOW:
        return CONFIDENCE_TIER_LOW
    if confidence == CONFIDENCE_MEDIUM:
        return CONFIDENCE_TIER_AVERAGE
    if confidence == CONFIDENCE_HIGH:
        return CONFIDENCE_TIER_HIGH
    return CONFIDENCE_TIER_NONE


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
        matrix[confidence_tier_key(row["confidence"])] += 1
    return matrix


def misconception_topics(answers_qs: QuerySet, limit: int = 10) -> list[dict]:
    """Topics with the most high-confidence wrong answers."""
    return list(
        answers_qs.filter(confidence=CONFIDENCE_HIGH, is_correct=False)
        .values("question__topic__name", "question__topic_id")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:limit]
    )

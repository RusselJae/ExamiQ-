"""Shared rule-based AI fallback helpers."""

from apps.analytics.confidence import (
    CLASSIFICATION_LUCKY_GUESS,
    CLASSIFICATION_MASTERY,
    CLASSIFICATION_MISCONCEPTION,
)


def calibration_narrative_from_matrix(matrix: dict, weak_topics: list | None = None) -> str:
    """Build a short confidence/score summary without calling an LLM."""
    parts = []
    misconception = matrix.get(CLASSIFICATION_MISCONCEPTION, 0)
    lucky = matrix.get(CLASSIFICATION_LUCKY_GUESS, 0)
    mastery = matrix.get(CLASSIFICATION_MASTERY, 0)

    if misconception >= 2:
        parts.append(
            f"Overconfidence pattern: {misconception} high-confidence wrong answers."
        )
    if lucky >= 2:
        parts.append(
            f"Anxiety pattern: {lucky} low-confidence correct answers."
        )
    if mastery >= 3 and not parts:
        parts.append("Strong match — most high-confidence answers are correct.")

    if weak_topics:
        names = ", ".join(
            t.get("topic__name", t.get("question__topic__name", "")) for t in weak_topics[:3]
        )
        if names:
            parts.append(f"Top mistake topics: {names}.")

    return " ".join(parts) if parts else "Not enough answer data for confidence insights yet."


def course_review_narrative(summary: dict) -> str:
    """Rule-based weekly review recommendation from course aggregates."""
    parts = []
    accuracy = summary.get("accuracy", 0)
    parts.append(f"Class accuracy is {accuracy}%.")

    misconceptions = summary.get("misconception_topics") or []
    if misconceptions:
        topics = ", ".join(
            item.get("question__topic__name", item.get("topic__name", ""))
            for item in misconceptions[:3]
        )
        parts.append(f"Prioritize in-class review for: {topics}.")

    mistakes = summary.get("mistake_patterns") or []
    if mistakes and not misconceptions:
        topics = ", ".join(item["topic__name"] for item in mistakes[:3])
        parts.append(f"Common mistake areas: {topics}.")

    return " ".join(parts)

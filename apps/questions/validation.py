"""Structural validation for professor question drafts."""

from __future__ import annotations

LABELS = ("A", "B", "C", "D")


def validate_question_structure(
    stem: str,
    choices: list[dict],
    correct_label: str = "",
) -> dict:
    """Return {is_valid: bool, errors: list[str]}."""
    errors: list[str] = []
    stem_clean = (stem or "").strip()
    if len(stem_clean) < 5:
        errors.append("Question stem is too short.")

    label = (correct_label or "A").strip().upper()
    if label not in LABELS:
        errors.append("Correct answer must be A, B, C, or D.")

    filled = []
    texts = []
    for choice in choices:
        text = (choice.get("text") or "").strip()
        if text:
            filled.append(choice)
            texts.append(text.lower())

    if len(filled) < 2:
        errors.append("At least two answer choices are required.")

    if len(filled) < 4:
        errors.append("All four choices (A-D) must be filled.")

    if len(texts) != len(set(texts)):
        errors.append("Answer choices must be distinct.")

    correct_count = sum(1 for c in filled if c.get("is_correct"))
    if correct_count != 1:
        errors.append("Exactly one choice must be marked correct.")

    correct_choice = next(
        (c for c in filled if (c.get("label") or "").upper() == label),
        None,
    )
    if not correct_choice or not (correct_choice.get("text") or "").strip():
        errors.append("Marked correct choice must have text.")

    return {"is_valid": not errors, "errors": errors}


def validate_question_for_submit(
    stem: str,
    choices: list[dict],
    topic,
    difficulty: str,
    correct_label: str = "",
    *,
    ai_enabled: bool = True,
) -> dict:
    """Structural + optional AI validation. Returns validator-shaped dict."""
    structure = validate_question_structure(stem, choices, correct_label)
    if not structure["is_valid"]:
        return {
            "is_valid": False,
            "topic_relevant": False,
            "answer_correct": False,
            "feedback": "; ".join(structure["errors"]),
            "suggested_concept_tag": "",
            "errors": structure["errors"],
        }

    from apps.ai.factory import get_question_validator

    result = get_question_validator().validate(stem, choices, topic, difficulty, correct_label)
    result["errors"] = structure["errors"]
    if not ai_enabled:
        result["is_valid"] = True
    elif not result.get("is_valid"):
        result["errors"] = structure["errors"] + [result.get("feedback") or "AI validation failed."]
    return result

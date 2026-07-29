"""Structural validation for professor question drafts."""

from __future__ import annotations

LABELS = ("A", "B", "C", "D")


def check_duplicate_stem(
    topic_id: int,
    stem: str,
    *,
    exclude_pk: int | None = None,
    peer_stems: list[str] | None = None,
) -> str | None:
    """Return an error message when stem exactly matches DB or peer queue entries."""
    from apps.questions.services import find_duplicate_question, normalize_stem

    normalized = normalize_stem(stem)
    if not normalized:
        return None

    if find_duplicate_question(topic_id, stem, exclude_pk=exclude_pk):
        return "Duplicate question: this stem already exists in the question bank."

    if peer_stems:
        for index, peer in enumerate(peer_stems, start=1):
            if normalize_stem(peer) == normalized:
                return f"Duplicate question: matches row {index} in your queue."
    return None


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


def validate_numeric_structure(
    stem: str,
    correct_answer: str | None,
) -> dict:
    """Return {is_valid: bool, errors: list[str]} for numeric questions."""
    errors: list[str] = []
    stem_clean = (stem or "").strip()
    if len(stem_clean) < 5:
        errors.append("Question stem is too short.")
    if correct_answer is None or str(correct_answer).strip() == "":
        errors.append("Numeric questions require a correct answer.")
    else:
        try:
            float(str(correct_answer).strip())
        except (TypeError, ValueError):
            errors.append("Correct answer must be a number.")
    return {"is_valid": not errors, "errors": errors}


def validate_question_for_submit(
    stem: str,
    choices: list[dict],
    topic,
    difficulty: str,
    correct_label: str = "",
    *,
    ai_enabled: bool = True,
    peer_stems: list[str] | None = None,
    exclude_pk: int | None = None,
    question_type: str = "mcq",
    correct_answer: str | None = None,
) -> dict:
    """Structural + duplicate + optional AI validation. Returns validator-shaped dict."""
    if question_type == "numeric":
        structure = validate_numeric_structure(stem, correct_answer)
    else:
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

    duplicate_message = check_duplicate_stem(
        topic.pk,
        stem,
        exclude_pk=exclude_pk,
        peer_stems=peer_stems,
    )
    if duplicate_message:
        return {
            "is_valid": False,
            "topic_relevant": False,
            "answer_correct": False,
            "feedback": duplicate_message,
            "suggested_concept_tag": "",
            "errors": [duplicate_message],
        }

    if question_type == "numeric" or not ai_enabled:
        return {
            "is_valid": True,
            "topic_relevant": True,
            "answer_correct": True,
            "feedback": "Structural checks passed." if question_type == "numeric" else "",
            "suggested_concept_tag": "",
            "errors": structure["errors"],
        }

    from apps.ai.factory import get_question_validator

    result = get_question_validator().validate(stem, choices, topic, difficulty, correct_label)
    result["errors"] = structure["errors"]
    if not result.get("is_valid"):
        result["errors"] = structure["errors"] + [result.get("feedback") or "AI validation failed."]
    return result

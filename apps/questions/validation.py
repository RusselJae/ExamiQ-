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


def validate_text_answer_structure(
    stem: str,
    expected_answer: str | None,
    *,
    question_type: str,
) -> dict:
    """Return {is_valid, errors} for True/False, Identification, Enumeration."""
    errors: list[str] = []
    stem_clean = (stem or "").strip()
    if len(stem_clean) < 5:
        errors.append("Question stem is too short.")

    expected = (expected_answer or "").strip()
    if not expected:
        errors.append("Expected answer is required for this question type.")
        return {"is_valid": False, "errors": errors}

    if question_type == "true_false":
        normalized = expected.casefold()
        if normalized not in {"true", "false", "t", "f", "yes", "no"}:
            errors.append("True/False expected answer must be True or False.")
    elif question_type == "enumeration":
        items = [
            part.strip()
            for part in expected.replace("|", "\n").replace(";", "\n").splitlines()
            if part.strip()
        ]
        if len(items) < 2:
            errors.append("Enumeration needs at least two expected items (one per line).")

    return {"is_valid": not errors, "errors": errors}


def _subject_relevance_block(
    stem: str,
    topic,
    *,
    ai_enabled: bool,
) -> dict | None:
    """Return a validation failure dict when the stem is off-subject."""
    stem_clean = (stem or "").strip()
    if not ai_enabled or topic is None or len(stem_clean) < 5:
        return None

    from apps.ai.subject_relevance import assess_question_subject_relevance

    subject = getattr(topic, "subject", None)
    if subject is None:
        return None

    relevance = assess_question_subject_relevance(stem_clean, subject, topic)
    if relevance.get("related"):
        return None

    code = getattr(subject, "code", "") or ""
    name = getattr(subject, "name", "") or "this course subject"
    feedback = (relevance.get("reason") or "").strip()
    if not feedback:
        feedback = (
            f"This question does not look related to {code} — {name}. "
            "Write a stem that matches this subject."
        )
    return {
        "is_valid": False,
        "topic_relevant": False,
        "answer_correct": False,
        "feedback": feedback,
        "suggested_concept_tag": "",
        "errors": [feedback],
    }


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
    expected_answer: str | None = None,
) -> dict:
    """Structural + duplicate + optional AI validation. Returns validator-shaped dict."""
    subject_block = _subject_relevance_block(stem, topic, ai_enabled=ai_enabled)
    if subject_block is not None:
        return subject_block

    if question_type == "numeric":
        structure = validate_numeric_structure(stem, correct_answer)
    elif question_type in {"true_false", "identification", "enumeration"}:
        structure = validate_text_answer_structure(
            stem, expected_answer, question_type=question_type
        )
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
    if not result.get("topic_relevant", True) and topic is not None:
        subject = getattr(topic, "subject", None)
        code = getattr(subject, "code", "") if subject else ""
        name = getattr(subject, "name", "") if subject else "this subject"
        if not (result.get("feedback") or "").strip() or code.lower() not in (
            result.get("feedback") or ""
        ).lower():
            result["feedback"] = (
                f"This question does not fit {code} — {name}. "
                f"{(result.get('feedback') or '').strip()}".strip()
            )
    if not result.get("is_valid"):
        result["errors"] = structure["errors"] + [result.get("feedback") or "AI validation failed."]
    return result

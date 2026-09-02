"""Post-process AI-generated question payloads for consistency."""

from __future__ import annotations

import json
import random
import re

from apps.ai.prompts import coerce_generate_question_type
from apps.questions.models import Question

LABELS = ("A", "B", "C", "D")
_BATCH_ROTATION = ("B", "C", "D", "A")
_FEEDBACK_JSON_KEYS = ("feedback", "why_wrong", "message", "text")


_LABEL_PREFIX_RE = re.compile(
    r"^(query|focus|redirect|instruction|note|context|metadata|system|response type)\s*:\s*",
    re.IGNORECASE,
)


def _strip_internal_meta_prefixes(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(_LABEL_PREFIX_RE.sub("", stripped).strip())
    return "\n".join(lines).strip()


def normalize_feedback_text(raw: str) -> str:
    """Return plain feedback text, stripping JSON wrappers when present."""
    text = (raw or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()

    candidates = [text]
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            for key in _FEEDBACK_JSON_KEYS:
                value = data.get(key)
                if value:
                    return _strip_internal_meta_prefixes(str(value).strip())

    return _strip_internal_meta_prefixes(text)


def _normalize_label(label: str) -> str:
    value = (label or "A").strip().upper()
    return value if value in LABELS else "A"


def reconcile_question_choices(question: dict) -> dict:
    """Ensure correct_label matches exactly one choice's is_correct flag."""
    choices = question.get("choices") or []
    correct_label = _normalize_label(question.get("correct_label", "A"))

    by_label = {
        _normalize_label(c.get("label")): (c.get("text") or "").strip()
        for c in choices
        if (c.get("text") or "").strip()
    }

    correct_text = by_label.get(correct_label, "")
    if not correct_text:
        flagged = [
            c for c in choices if c.get("is_correct") and (c.get("text") or "").strip()
        ]
        if len(flagged) == 1:
            correct_text = (flagged[0].get("text") or "").strip()
            correct_label = _normalize_label(flagged[0].get("label", correct_label))

    distractor_texts = [text for label, text in by_label.items() if label != correct_label]
    while len(distractor_texts) < 3:
        distractor_texts.append("")

    normalized_choices = []
    distractor_index = 0
    for label in LABELS:
        if label == correct_label:
            text = correct_text
        else:
            text = distractor_texts[distractor_index]
            distractor_index += 1
        normalized_choices.append({
            "label": label,
            "text": text,
            "is_correct": label == correct_label,
        })

    question["correct_label"] = correct_label
    question["choices"] = normalized_choices
    return question


def randomize_choice_positions(question: dict, rng: random.Random) -> dict:
    """Move the correct answer text to a random A-D slot."""
    question = reconcile_question_choices(dict(question))
    choices = question["choices"]
    correct_text = next((c["text"] for c in choices if c["is_correct"]), "")
    distractor_texts = [c["text"] for c in choices if not c["is_correct"] and c["text"]]
    while len(distractor_texts) < 3:
        distractor_texts.append("")

    new_correct = rng.choice(LABELS)
    pool = distractor_texts[:]
    rng.shuffle(pool)

    new_choices = []
    pool_index = 0
    for label in LABELS:
        if label == new_correct:
            text = correct_text
        else:
            text = pool[pool_index] if pool_index < len(pool) else ""
            pool_index += 1
        new_choices.append({
            "label": label,
            "text": text,
            "is_correct": label == new_correct,
        })

    question["correct_label"] = new_correct
    question["choices"] = new_choices
    return question


def _move_correct_to_label(question: dict, target_label: str) -> dict:
    """Place the correct answer text on a specific choice letter."""
    target_label = _normalize_label(target_label)
    question = reconcile_question_choices(dict(question))
    choices = question["choices"]
    correct_text = next((c["text"] for c in choices if c["is_correct"]), "")
    distractor_texts = [c["text"] for c in choices if not c["is_correct"] and c["text"]]
    while len(distractor_texts) < 3:
        distractor_texts.append("")

    new_choices = []
    distractor_index = 0
    for label in LABELS:
        if label == target_label:
            text = correct_text
        else:
            text = distractor_texts[distractor_index]
            distractor_index += 1
        new_choices.append({
            "label": label,
            "text": text,
            "is_correct": label == target_label,
        })

    question["correct_label"] = target_label
    question["choices"] = new_choices
    return question


def _vary_batch_positions(questions: list[dict]) -> list[dict]:
    """Ensure a batch does not share one correct letter when avoidable."""
    if len(questions) <= 1:
        return questions

    labels = [q["correct_label"] for q in questions]
    if len(set(labels)) > 1:
        return questions

    for index in range(1, len(questions)):
        target = _BATCH_ROTATION[index % len(_BATCH_ROTATION)]
        questions[index] = _move_correct_to_label(questions[index], target)
    return questions


def _coerce_text(value) -> str:
    """Coerce model JSON values (bool/int/list) into a comparable string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "\n".join(_coerce_text(item) for item in value if _coerce_text(item))
    return str(value).strip()


def _normalize_true_false_answer(value) -> str:
    text = _coerce_text(value).casefold()
    if text in {"true", "t", "yes", "1"}:
        return "True"
    if text in {"false", "f", "no", "0"}:
        return "False"
    return _coerce_text(value)


def _normalize_identification_answer(value) -> str:
    return re.sub(r"\s+", " ", _coerce_text(value))


def _normalize_enumeration_answer(value) -> str:
    if isinstance(value, (list, tuple)):
        items = [_coerce_text(part) for part in value]
        items = [re.sub(r"\s+", " ", item) for item in items if item]
        return "\n".join(items)
    parts = re.split(r"[\n|;]+", _coerce_text(value))
    items = [re.sub(r"\s+", " ", part.strip()) for part in parts if part.strip()]
    return "\n".join(items)


def _normalize_generated_item(raw: dict, rng: random.Random) -> dict:
    item = dict(raw)
    item.pop("explanation_steps", None)
    item.pop("solution_summary", None)

    qtype = coerce_generate_question_type(item.get("question_type"))
    item["question_type"] = qtype
    item["stem"] = _coerce_text(item.get("stem"))
    item["concept_tag"] = _coerce_text(item.get("concept_tag"))

    if qtype == Question.QuestionType.MCQ:
        return randomize_choice_positions(item, rng)

    item.pop("choices", None)
    item.pop("correct_label", None)
    expected = item.get("expected_answer")
    if qtype == Question.QuestionType.TRUE_FALSE:
        item["expected_answer"] = _normalize_true_false_answer(expected)
    elif qtype == Question.QuestionType.IDENTIFICATION:
        item["expected_answer"] = _normalize_identification_answer(expected)
    elif qtype == Question.QuestionType.ENUMERATION:
        item["expected_answer"] = _normalize_enumeration_answer(expected)
    else:
        item["expected_answer"] = _coerce_text(expected)
    return item


def normalize_generated_questions(
    questions: list[dict],
    rng: random.Random | None = None,
    *,
    question_type: str | None = None,
) -> list[dict]:
    """Normalize AI question payloads for the requested type."""
    if not questions:
        return []

    randomizer = rng or random.Random()
    default_type = coerce_generate_question_type(question_type) if question_type else None
    result: list[dict] = []
    for raw in questions:
        payload = dict(raw)
        if default_type and not payload.get("question_type"):
            payload["question_type"] = default_type
        result.append(_normalize_generated_item(payload, randomizer))

    if result and result[0].get("question_type") == Question.QuestionType.MCQ:
        return _vary_batch_positions(result)
    return result

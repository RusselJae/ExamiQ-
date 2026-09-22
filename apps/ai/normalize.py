"""Post-process AI-generated question payloads for consistency."""

from __future__ import annotations

import json
import random
import re

from apps.ai.prompts import coerce_generate_question_type
from apps.questions.models import Question

LABELS = ("A", "B", "C", "D")
_BATCH_ROTATION = ("B", "C", "D", "A")
_FEEDBACK_JSON_KEYS = (
    "feedback",
    "why_wrong",
    "what_went_wrong",
    "why",
    "message",
    "text",
)

_STEP_PATTERN_RE = re.compile(r"\bStep\s*\d+\s*[.:)\-]", re.IGNORECASE)
_FILLER_RE = re.compile(
    r"\b(great try|double-?check your work|remember to|since you have|"
    r"high confidence|low confidence|keep practicing|you'?ve got this)\b",
    re.IGNORECASE,
)
_FIELD_MAX_CHARS = 420
_SOLUTION_STEP_MAX_CHARS = 800
_SOLUTION_STEPS_MAX = 12
_REMEMBER_MAX_WORDS = 10
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


def _extract_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
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
            return data
    return None


def normalize_feedback_text(raw: str) -> str:
    """Return plain feedback text, stripping JSON wrappers when present."""
    text = (raw or "").strip()
    if not text:
        return ""

    data = _extract_json_object(text)
    if data:
        # Prefer structured adaptive fields when present.
        structured = parse_adaptive_feedback(data)
        if structured:
            parts = [
                structured.get("what_went_wrong") or "",
                structured.get("why") or "",
            ]
            joined = " ".join(p for p in parts if p).strip()
            if joined:
                return _strip_internal_meta_prefixes(joined)
        correct = parse_correct_adaptive_feedback(data)
        if correct:
            parts = [
                correct.get("why_it_works") or "",
                correct.get("remember") or "",
            ]
            joined = " ".join(p for p in parts if p).strip()
            if joined:
                return _strip_internal_meta_prefixes(joined)
        for key in _FEEDBACK_JSON_KEYS:
            value = data.get(key)
            if value:
                return _strip_internal_meta_prefixes(str(value).strip())

    return _strip_internal_meta_prefixes(text)


def parse_adaptive_feedback(raw: str | dict | None) -> dict | None:
    """Parse and lightly normalize structured adaptive feedback, or return None."""
    if isinstance(raw, dict):
        data = raw
    else:
        data = _extract_json_object(str(raw or ""))
    if not data:
        return None
    if not any(k in data for k in ("what_went_wrong", "why", "remember")):
        return None

    quick = data.get("quick_check")
    if quick is None or str(quick).strip().lower() in {"", "null", "none"}:
        quick_check = None
    else:
        quick_check = str(quick).strip()

    follow_ups_raw = data.get("follow_ups") or []
    follow_ups: list[str] = []
    if isinstance(follow_ups_raw, list):
        for item in follow_ups_raw:
            text = str(item or "").strip()
            if text:
                follow_ups.append(text)
    follow_ups = follow_ups[:3]

    solution_steps = _parse_solution_steps(data.get("solution_steps"))

    return {
        "what_went_wrong": str(data.get("what_went_wrong") or "").strip(),
        "why": str(data.get("why") or "").strip(),
        "quick_check": quick_check,
        "remember": str(data.get("remember") or "").strip(),
        "follow_ups": follow_ups,
        "solution_steps": solution_steps,
    }


def _parse_solution_steps(raw: object | None) -> list[str] | None:
    """Normalize optional solution_steps list; null/empty → None."""
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text.lower() in {"null", "none"}:
            return None
        return [text]
    if not isinstance(raw, list):
        return None
    steps: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            steps.append(text)
        if len(steps) >= _SOLUTION_STEPS_MAX:
            break
    return steps or None


def validate_adaptive_feedback(raw: str | dict | None) -> dict | None:
    """
    Validate structured adaptive feedback.

    Rejects empty required fields, Step-N patterns (except in solution_steps),
    filler, overlong fields, or a remember hook longer than 10 words.
    Returns a cleaned dict or None.
    """
    parsed = parse_adaptive_feedback(raw)
    if not parsed:
        return None

    required = ("what_went_wrong", "why", "remember")
    for key in required:
        value = parsed.get(key) or ""
        if not value:
            return None
        if len(value) > _FIELD_MAX_CHARS:
            return None
        if _STEP_PATTERN_RE.search(value) or _FILLER_RE.search(value):
            return None

    quick = parsed.get("quick_check")
    if quick is not None:
        if not quick or len(quick) > _FIELD_MAX_CHARS:
            return None
        if _STEP_PATTERN_RE.search(quick) or _FILLER_RE.search(quick):
            return None

    remember_words = [w for w in parsed["remember"].split() if w]
    if len(remember_words) > _REMEMBER_MAX_WORDS:
        return None

    follow_ups = parsed.get("follow_ups") or []
    if len(follow_ups) < 1:
        return None
    cleaned_follow_ups = []
    for item in follow_ups:
        if len(item) > 120 or _FILLER_RE.search(item):
            continue
        cleaned_follow_ups.append(item)
    if len(cleaned_follow_ups) < 1:
        return None
    parsed["follow_ups"] = cleaned_follow_ups[:3]

    steps = parsed.get("solution_steps")
    if steps is not None:
        cleaned_steps: list[str] = []
        for step in steps:
            if not step or len(step) > _SOLUTION_STEP_MAX_CHARS:
                continue
            if _FILLER_RE.search(step):
                continue
            cleaned_steps.append(step)
            if len(cleaned_steps) >= _SOLUTION_STEPS_MAX:
                break
        parsed["solution_steps"] = cleaned_steps or None
    return parsed


def adaptive_feedback_to_json(data: dict) -> str:
    """Serialize validated adaptive feedback for storage."""
    if data.get("kind") == "correct" or "why_it_works" in data:
        return correct_adaptive_feedback_to_json(data)
    payload = {
        "what_went_wrong": data.get("what_went_wrong") or "",
        "why": data.get("why") or "",
        "quick_check": data.get("quick_check"),
        "remember": data.get("remember") or "",
        "follow_ups": list(data.get("follow_ups") or [])[:3],
        "solution_steps": data.get("solution_steps"),
    }
    return json.dumps(payload, ensure_ascii=False)


def parse_correct_adaptive_feedback(raw: str | dict | None) -> dict | None:
    """Parse structured correct-answer adaptive feedback, or return None."""
    if isinstance(raw, dict):
        data = raw
    else:
        data = _extract_json_object(str(raw or ""))
    if not data or "why_it_works" not in data:
        return None

    worked = data.get("worked_example")
    if worked is None or str(worked).strip().lower() in {"", "null", "none"}:
        worked_example = None
    else:
        worked_example = str(worked).strip()

    follow_ups_raw = data.get("follow_ups") or []
    follow_ups: list[str] = []
    if isinstance(follow_ups_raw, list):
        for item in follow_ups_raw:
            text = str(item or "").strip()
            if text:
                follow_ups.append(text)
    follow_ups = follow_ups[:3]

    why = str(data.get("why_it_works") or "").strip()
    remember = str(data.get("remember") or "").strip()
    if not why and not remember:
        return None

    return {
        "kind": "correct",
        "why_it_works": why,
        "remember": remember,
        "worked_example": worked_example,
        "follow_ups": follow_ups,
    }


def validate_correct_adaptive_feedback(raw: str | dict | None) -> dict | None:
    """Validate correct-answer adaptive feedback; return cleaned dict or None."""
    parsed = parse_correct_adaptive_feedback(raw)
    if not parsed:
        return None

    for key in ("why_it_works", "remember"):
        value = parsed.get(key) or ""
        if not value:
            return None
        if len(value) > _FIELD_MAX_CHARS:
            return None
        if _STEP_PATTERN_RE.search(value) or _FILLER_RE.search(value):
            return None

    worked = parsed.get("worked_example")
    if worked is not None:
        if not worked or len(worked) > _FIELD_MAX_CHARS:
            return None
        if _STEP_PATTERN_RE.search(worked) or _FILLER_RE.search(worked):
            return None

    remember_words = [w for w in parsed["remember"].split() if w]
    if len(remember_words) > _REMEMBER_MAX_WORDS:
        return None

    follow_ups = parsed.get("follow_ups") or []
    if len(follow_ups) < 1:
        return None
    cleaned_follow_ups = []
    for item in follow_ups:
        if len(item) > 120 or _FILLER_RE.search(item):
            continue
        cleaned_follow_ups.append(item)
    if len(cleaned_follow_ups) < 1:
        return None
    parsed["follow_ups"] = cleaned_follow_ups[:3]
    return parsed


def correct_adaptive_feedback_to_json(data: dict) -> str:
    """Serialize validated correct adaptive feedback for storage."""
    payload = {
        "why_it_works": data.get("why_it_works") or "",
        "remember": data.get("remember") or "",
        "worked_example": data.get("worked_example"),
        "follow_ups": list(data.get("follow_ups") or [])[:3],
    }
    return json.dumps(payload, ensure_ascii=False)


def parse_any_adaptive_feedback(raw: str | dict | None) -> dict | None:
    """Parse incorrect or correct adaptive feedback (correct preferred when both keys exist)."""
    correct = parse_correct_adaptive_feedback(raw)
    if correct and (correct.get("why_it_works") or "").strip():
        # Prefer correct schema when why_it_works is present.
        if isinstance(raw, dict):
            if "why_it_works" in raw:
                return correct
        else:
            text = str(raw or "")
            if "why_it_works" in text:
                return correct
    incorrect = parse_adaptive_feedback(raw)
    if incorrect:
        incorrect = dict(incorrect)
        incorrect["kind"] = "incorrect"
        return incorrect
    return correct


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


def _normalize_explanation_fields(item: dict) -> None:
    """Keep cleaned explanation + adaptive fields on a generated item."""
    from apps.questions.services import clean_adaptive_explanation

    steps_raw = item.get("explanation_steps")
    steps: list[str] = []
    if isinstance(steps_raw, list):
        for part in steps_raw:
            text = _coerce_text(part)
            if text:
                steps.append(text)
    elif steps_raw is not None:
        text = _coerce_text(steps_raw)
        if text:
            steps.append(text)
    item["explanation_steps"] = steps
    item["solution_summary"] = _coerce_text(item.get("solution_summary"))

    adaptive = clean_adaptive_explanation(item)
    for key, value in adaptive.items():
        item[key] = value


def _normalize_generated_item(raw: dict, rng: random.Random) -> dict:
    item = dict(raw)
    _normalize_explanation_fields(item)

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

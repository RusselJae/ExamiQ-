"""Post-process AI-generated question payloads for consistency."""

from __future__ import annotations

import random

LABELS = ("A", "B", "C", "D")
_BATCH_ROTATION = ("B", "C", "D", "A")


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


def normalize_generated_questions(
    questions: list[dict],
    rng: random.Random | None = None,
) -> list[dict]:
    """Reconcile choices and randomize correct-answer positions."""
    if not questions:
        return []

    randomizer = rng or random.Random()
    result = [
        randomize_choice_positions(dict(raw), randomizer)
        for raw in questions
    ]
    return _vary_batch_positions(result)

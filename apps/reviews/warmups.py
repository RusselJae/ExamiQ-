"""Fixed warm-up MCQ bank for the pre-exam modal flow."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class WarmupQuestion:
    stem: str
    choices: tuple[str, ...]
    correct_index: int
    feedback_correct: str
    feedback_incorrect: str


WARMUP_BANK: tuple[WarmupQuestion, ...] = (
    WarmupQuestion(
        stem="Which fraction is larger?",
        choices=("1/2", "1/3", "They are equal"),
        correct_index=0,
        feedback_correct="Correct — 1/2 is larger than 1/3.",
        feedback_incorrect="Not quite — compare the denominators: 1/2 is larger than 1/3.",
    ),
    WarmupQuestion(
        stem="What is 7 × 8?",
        choices=("54", "56", "64"),
        correct_index=1,
        feedback_correct="Correct — 7 × 8 = 56.",
        feedback_incorrect="Not quite — 7 × 8 = 56.",
    ),
    WarmupQuestion(
        stem="Which value is greater?",
        choices=("0.75", "0.7", "They are equal"),
        correct_index=0,
        feedback_correct="Correct — 0.75 is greater than 0.7.",
        feedback_incorrect="Not quite — 0.75 is greater than 0.7.",
    ),
    WarmupQuestion(
        stem="How many sides does a hexagon have?",
        choices=("5", "6", "8"),
        correct_index=1,
        feedback_correct="Correct — a hexagon has 6 sides.",
        feedback_incorrect="Not quite — a hexagon has 6 sides.",
    ),
)


def random_warmup() -> dict:
    """Return a warmup question as a JSON-serializable dict."""
    q = random.choice(WARMUP_BANK)
    return {
        "stem": q.stem,
        "choices": [{"index": i, "text": text} for i, text in enumerate(q.choices)],
        "correct_index": q.correct_index,
        "feedback_correct": q.feedback_correct,
        "feedback_incorrect": q.feedback_incorrect,
    }

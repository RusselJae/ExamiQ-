"""Adaptive per-answer feedback generation with validation + one retry."""

from __future__ import annotations

import logging

from apps.ai.normalize import (
    adaptive_feedback_to_json,
    correct_adaptive_feedback_to_json,
    validate_adaptive_feedback,
    validate_correct_adaptive_feedback,
)
from apps.ai.prompts import (
    adaptive_feedback_max_tokens,
    build_adaptive_feedback_prompt,
    build_correct_adaptive_feedback_prompt,
)
from apps.ai.stubs import StubAdaptiveFeedbackGenerator

logger = logging.getLogger(__name__)


def generate_validated_adaptive_feedback(
    *,
    chat_json,
    topic: str,
    question: str,
    user_answer: str,
    correct_answer: str,
    confidence: str = "medium",
    question_type: str = "",
    choices: list[str] | None = None,
    difficulty: str = "",
    is_correct: bool = False,
    unanswered: bool = False,
) -> str:
    """
    Call ``chat_json(system, prompt, max_tokens) -> str|None`` up to twice.

    Returns a validated JSON string, or the stub payload when generation fails.
    """
    stub = StubAdaptiveFeedbackGenerator()
    if is_correct:
        system, prompt = build_correct_adaptive_feedback_prompt(
            topic,
            question,
            user_answer,
            correct_answer,
            confidence,
            question_type=question_type,
            choices=choices,
            difficulty=difficulty,
        )
        validate = validate_correct_adaptive_feedback
        to_json = correct_adaptive_feedback_to_json
    else:
        system, prompt = build_adaptive_feedback_prompt(
            topic,
            question,
            user_answer,
            correct_answer,
            confidence,
            question_type=question_type,
            choices=choices,
            difficulty=difficulty,
            unanswered=unanswered,
        )
        validate = validate_adaptive_feedback
        to_json = adaptive_feedback_to_json

    max_tokens = adaptive_feedback_max_tokens()

    for attempt in range(2):
        raw = None
        try:
            raw = chat_json(system, prompt, max_tokens)
        except Exception as exc:
            logger.warning("Adaptive feedback attempt %s failed: %s", attempt + 1, exc)
            raw = None
        validated = validate(raw)
        if validated:
            return to_json(validated)
        logger.info(
            "Adaptive feedback attempt %s rejected by validator",
            attempt + 1,
        )

    return stub.generate(
        topic,
        question,
        user_answer,
        correct_answer,
        confidence,
        question_type=question_type,
        choices=choices,
        difficulty=difficulty,
        is_correct=is_correct,
        unanswered=unanswered,
    )

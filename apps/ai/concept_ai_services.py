"""Concept remediation and practice generation with validation + retry."""

from __future__ import annotations

import logging
from typing import Any, Callable

from apps.ai.normalize import (
    validate_concept_practice_question,
    validate_concept_remediation,
)
from apps.ai.prompts import (
    build_concept_practice_question_prompt,
    build_concept_remediation_prompt,
    concept_practice_max_tokens,
    concept_remediation_max_tokens,
)
from apps.ai.stubs import (
    StubConceptPracticeGenerator,
    StubConceptRemediationGenerator,
)

logger = logging.getLogger(__name__)

ChatJsonFn = Callable[[str, str, int], str | None]


def generate_validated_concept_remediation(
    *,
    chat_json: ChatJsonFn,
    concept_name: str,
    subject: str,
    topic: str,
    difficulty: str = "beginner",
    miss_count: int = 1,
    missed_questions: list | None = None,
    previous_feedback_styles: list | None = None,
    student_stage: str = "first_review",
    prerequisites: list | None = None,
    preferred_style: str = "worked_example",
) -> dict[str, Any]:
    """Call chat_json up to twice; return validated remediation or stub."""
    system, prompt = build_concept_remediation_prompt(
        concept_name=concept_name,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        miss_count=miss_count,
        missed_questions=missed_questions,
        previous_feedback_styles=previous_feedback_styles,
        student_stage=student_stage,
        prerequisites=prerequisites,
        preferred_style=preferred_style,
    )
    max_tokens = concept_remediation_max_tokens()

    for attempt in range(2):
        raw = None
        try:
            raw = chat_json(system, prompt, max_tokens)
        except Exception as exc:
            logger.warning("Concept remediation attempt %s failed: %s", attempt + 1, exc)
            raw = None
        validated = validate_concept_remediation(raw)
        if validated:
            return validated
        logger.info("Concept remediation attempt %s rejected by validator", attempt + 1)

    return StubConceptRemediationGenerator().generate(
        concept_name=concept_name,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        miss_count=miss_count,
        missed_questions=missed_questions,
        previous_feedback_styles=previous_feedback_styles,
        student_stage=student_stage,
        prerequisites=prerequisites,
        preferred_style=preferred_style,
    )


def generate_validated_concept_practice(
    *,
    chat_json: ChatJsonFn,
    concept_name: str,
    subject: str,
    topic: str,
    difficulty: str = "beginner",
    attempt_number: int = 1,
    known_error_tags: list | None = None,
    previous_questions: list | None = None,
    prerequisite_mode: bool = False,
    prerequisite_concept: str = "",
) -> dict[str, Any]:
    """Call chat_json up to twice; return validated practice MCQ or stub."""
    system, prompt = build_concept_practice_question_prompt(
        concept_name=concept_name,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        attempt_number=attempt_number,
        known_error_tags=known_error_tags,
        previous_questions=previous_questions,
        prerequisite_mode=prerequisite_mode,
        prerequisite_concept=prerequisite_concept,
    )
    max_tokens = concept_practice_max_tokens()

    for attempt in range(2):
        raw = None
        try:
            raw = chat_json(system, prompt, max_tokens)
        except Exception as exc:
            logger.warning("Concept practice attempt %s failed: %s", attempt + 1, exc)
            raw = None
        validated = validate_concept_practice_question(raw)
        if validated:
            return validated
        logger.info("Concept practice attempt %s rejected by validator", attempt + 1)

    return StubConceptPracticeGenerator().generate(
        concept_name=concept_name,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        attempt_number=attempt_number,
        known_error_tags=known_error_tags,
        previous_questions=previous_questions,
        prerequisite_mode=prerequisite_mode,
        prerequisite_concept=prerequisite_concept,
    )

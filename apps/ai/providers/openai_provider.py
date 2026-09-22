"""OpenAI-backed AI service implementations."""

import json
import logging
import re

from django.conf import settings

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.helpers import calibration_narrative_from_matrix, course_review_narrative
from apps.ai.prompts import (
    build_calibration_prompt,
    build_course_report_prompt,
    build_difficulty_tag_prompt,
    build_explanation_generation_prompt,
    build_question_generation_prompt,
    build_question_validation_prompt,
    validation_max_tokens,
)
from apps.ai.interfaces import (
    AdaptiveFeedbackGenerator,
    CalibrationAnalyzer,
    CurriculumAdvisor,
    DifficultyTagger,
    ErrorClassifier,
    ExplanationGenerator,
    QuestionGenerator,
    QuestionValidator,
)
from apps.ai.stubs import (
    StubCalibrationAnalyzer,
    StubCurriculumAdvisor,
    StubDifficultyTagger,
    StubErrorClassifier,
    StubQuestionValidator,
)
from apps.analytics.confidence import confidence_accuracy_matrix
from apps.analytics.models import ErrorType
from apps.analytics.services import course_performance_summary
from apps.questions.models import Question

logger = logging.getLogger(__name__)

_VALID_DIFFICULTIES = {c.value for c in Question.Difficulty}


def _get_client():
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _chat(
    prompt: str,
    system: str = "You are a concise educational analytics assistant.",
    max_output_tokens: int = 500,
    *,
    json_mode: bool = False,
) -> str | None:
    try:
        client = _get_client()
        kwargs: dict = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": max_output_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("OpenAI API call failed: %s", exc)
        return None


class OpenAICalibrationAnalyzer(CalibrationAnalyzer):
    def analyze(self, student, answers_qs, weak_topics: list | None = None) -> dict:
        matrix = confidence_accuracy_matrix(answers_qs)
        fallback = calibration_narrative_from_matrix(matrix, weak_topics)
        prompt = build_calibration_prompt(matrix, weak_topics)
        narrative = _chat(prompt) or fallback
        return {"matrix": matrix, "narrative": narrative, "ai_enabled": True}


class OpenAICurriculumAdvisor(CurriculumAdvisor):
    def course_report(self, course) -> str:
        summary = course_performance_summary(course)
        fallback = course_review_narrative(summary)
        prompt = build_course_report_prompt(course, summary)
        return _chat(prompt) or fallback


class OpenAIDifficultyTagger(DifficultyTagger):
    def tag(self, stem: str, current_difficulty: str) -> str:
        stub = StubDifficultyTagger()
        if not stem.strip():
            return current_difficulty
        system, prompt = build_difficulty_tag_prompt(stem)
        result = _chat(prompt, system=system)
        if result:
            normalized = result.lower().strip().strip(".")
            if normalized in _VALID_DIFFICULTIES:
                return normalized
        return stub.tag(stem, current_difficulty)


class OpenAIQuestionGenerator(QuestionGenerator):
    def generate(
        self,
        topic,
        difficulty: str,
        count: int = 5,
        reference_stem: str = "",
        source_material: str = "",
        question_type: str = "mcq",
    ):
        if topic is None:
            return []
        system, user_prompt, max_tokens = build_question_generation_prompt(
            topic,
            difficulty,
            count,
            reference_stem,
            source_material=source_material,
            question_type=question_type,
        )
        token_budgets = [max_tokens, min(max_tokens * 2, 4096)]
        last_raw = ""
        last_exc: json.JSONDecodeError | TypeError | None = None

        for budget in token_budgets:
            raw = _chat(user_prompt, system=system, max_output_tokens=budget)
            if not raw:
                raise AIServiceUnavailableError(
                    "AI service is temporarily unavailable. Please try again later.",
                    retryable=True,
                )
            last_raw = raw
            try:
                cleaned = raw
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                if match:
                    cleaned = match.group(0)
                data = json.loads(cleaned)
                if isinstance(data, list):
                    from apps.ai.normalize import normalize_generated_questions

                    return normalize_generated_questions(
                        data[:count],
                        question_type=question_type,
                    )
            except (json.JSONDecodeError, TypeError) as exc:
                last_exc = exc
                logger.warning(
                    "Failed to parse OpenAI question JSON (budget=%s): %s",
                    budget,
                    exc,
                )

        raise AIServiceUnavailableError(
            "AI returned incomplete or invalid JSON. Try again with fewer questions.",
            detail=str(last_exc) if last_exc else last_raw[:500],
            retryable=True,
        )


class OpenAIExplanationGenerator(ExplanationGenerator):
    def generate(self, question) -> dict:
        system, user_prompt, max_tokens = build_explanation_generation_prompt(question)
        token_budgets = [max_tokens, min(max_tokens * 2, 4096)]
        last_raw = ""
        last_exc: json.JSONDecodeError | TypeError | None = None

        for budget in token_budgets:
            raw = _chat(user_prompt, system=system, max_output_tokens=budget)
            if not raw:
                raise AIServiceUnavailableError(
                    "AI service is temporarily unavailable. Please try again later.",
                    retryable=True,
                )
            last_raw = raw
            try:
                cleaned = raw
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    cleaned = match.group(0)
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    steps = data.get("explanation_steps") or []
                    if not isinstance(steps, list):
                        steps = []
                    payload = {
                        "explanation_steps": [
                            str(s).strip() for s in steps if str(s).strip()
                        ],
                        "solution_summary": str(
                            data.get("solution_summary") or ""
                        ).strip(),
                        "what_went_wrong": str(
                            data.get("what_went_wrong") or ""
                        ).strip(),
                        "why": str(data.get("why") or "").strip(),
                        "quick_check": data.get("quick_check"),
                        "remember": str(data.get("remember") or "").strip(),
                        "worked_example": data.get("worked_example"),
                    }
                    if (
                        payload["explanation_steps"]
                        or payload["solution_summary"]
                        or payload["what_went_wrong"]
                    ):
                        return payload
            except (json.JSONDecodeError, TypeError) as exc:
                last_exc = exc
                logger.warning(
                    "Failed to parse OpenAI explanation JSON (budget=%s): %s",
                    budget,
                    exc,
                )

        raise AIServiceUnavailableError(
            "AI returned incomplete explanation JSON. Please try again.",
            detail=str(last_exc) if last_exc else last_raw[:500],
            retryable=True,
        )


class OpenAIQuestionValidator(QuestionValidator):
    def validate(self, stem, choices, topic, difficulty, correct_label=""):
        from apps.ai.stubs import StubQuestionValidator

        stub = StubQuestionValidator()
        if not stem.strip():
            return {
                "is_valid": False,
                "topic_relevant": False,
                "answer_correct": False,
                "feedback": "Question stem is empty.",
                "suggested_concept_tag": "",
            }
        system, prompt = build_question_validation_prompt(
            stem, choices, topic, difficulty, correct_label
        )
        raw = _chat(prompt, system=system, max_output_tokens=validation_max_tokens())
        if not raw:
            return stub.validate(stem, choices, topic, difficulty, correct_label)
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to parse validation JSON: %s", exc)
        return stub.validate(stem, choices, topic, difficulty, correct_label)


class OpenAIAdaptiveFeedbackGenerator(AdaptiveFeedbackGenerator):
    def generate(
        self,
        topic: str,
        question: str,
        user_answer: str,
        correct_answer: str,
        confidence: str = "medium",
        question_type: str = "",
        *,
        choices: list[str] | None = None,
        difficulty: str = "",
        is_correct: bool = False,
        unanswered: bool = False,
        shared_base: dict | None = None,
    ) -> str:
        from apps.ai.feedback_services import generate_validated_adaptive_feedback

        def chat_json(system: str, prompt: str, max_tokens: int) -> str | None:
            return _chat(
                prompt,
                system=system,
                max_output_tokens=max_tokens,
                json_mode=True,
            )

        return generate_validated_adaptive_feedback(
            chat_json=chat_json,
            topic=topic,
            question=question,
            user_answer=user_answer,
            correct_answer=correct_answer,
            confidence=confidence,
            question_type=question_type,
            choices=choices,
            difficulty=difficulty,
            is_correct=is_correct,
            unanswered=unanswered,
            shared_base=shared_base,
        )


class OpenAIErrorClassifier(ErrorClassifier):
    def classify(self, question, answer):
        if not answer.selected_choice_id:
            return None
        error_types = list(ErrorType.objects.values("slug", "label", "category"))
        if not error_types:
            return None
        prompt = (
            f"Question: {question.stem}\n"
            f"Wrong choice: {answer.selected_choice.text}\n"
            f"Error types: {json.dumps(error_types)}\n"
            "If confident, reply with only the matching slug. Otherwise reply NONE."
        )
        result = _chat(prompt, system="Reply with an error type slug or NONE.")
        if not result or result.upper() == "NONE":
            return None
        slug = result.lower().strip().strip(".")
        return ErrorType.objects.filter(slug=slug).first()

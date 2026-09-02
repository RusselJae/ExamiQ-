"""Gemini-backed AI service implementations."""

import json
import logging
import re

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.helpers import calibration_narrative_from_matrix, course_review_narrative
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
from apps.ai.prompts import (
    adaptive_feedback_max_tokens,
    build_adaptive_feedback_prompt,
    build_calibration_prompt,
    build_course_report_prompt,
    build_difficulty_tag_prompt,
    build_explanation_generation_prompt,
    build_question_generation_prompt,
    build_question_validation_prompt,
    validation_max_tokens,
)
from apps.ai.providers import gemini_client
from apps.ai.stubs import (
    StubAdaptiveFeedbackGenerator,
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


def _parse_question_json(raw: str) -> list[dict]:
    """Extract and parse a JSON array from model output."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    text = re.sub(r",\s*]", "]", text)
    text = re.sub(r",\s*}", "}", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise json.JSONDecodeError("Expected JSON array", text, 0)
    return data


def _parse_explanation_json(raw: str) -> dict:
    """Extract and parse an explanation JSON object from model output."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    text = re.sub(r",\s*]", "]", text)
    text = re.sub(r",\s*}", "}", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("Expected JSON object", text, 0)
    steps = data.get("explanation_steps") or []
    if not isinstance(steps, list):
        steps = []
    return {
        "explanation_steps": [str(s).strip() for s in steps if str(s).strip()],
        "solution_summary": str(data.get("solution_summary") or "").strip(),
    }


def _chat(prompt: str, system: str = "You are a concise educational analytics assistant.", max_output_tokens: int = 500) -> str | None:
    return gemini_client.chat(prompt, system=system, max_output_tokens=max_output_tokens)


class GeminiCalibrationAnalyzer(CalibrationAnalyzer):
    def analyze(self, student, answers_qs, weak_topics: list | None = None) -> dict:
        matrix = confidence_accuracy_matrix(answers_qs)
        fallback = calibration_narrative_from_matrix(matrix, weak_topics)
        prompt = build_calibration_prompt(matrix, weak_topics)
        narrative = _chat(prompt) or fallback
        return {"matrix": matrix, "narrative": narrative, "ai_enabled": True}


class GeminiCurriculumAdvisor(CurriculumAdvisor):
    def course_report(self, course) -> str:
        summary = course_performance_summary(course)
        fallback = course_review_narrative(summary)
        prompt = build_course_report_prompt(course, summary)
        return _chat(prompt) or fallback


class GeminiDifficultyTagger(DifficultyTagger):
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


class GeminiQuestionGenerator(QuestionGenerator):
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
            result = gemini_client.chat_with_fallback(
                user_prompt,
                system=system,
                max_output_tokens=budget,
                json_mode=True,
            )
            last_raw = result.text
            try:
                data = _parse_question_json(last_raw)
                if data:
                    from apps.ai.normalize import normalize_generated_questions

                    return normalize_generated_questions(
                        data[:count],
                        question_type=question_type,
                    )
            except (json.JSONDecodeError, TypeError) as exc:
                last_exc = exc
                logger.warning(
                    "Failed to parse Gemini question JSON (budget=%s): %s",
                    budget,
                    exc,
                )

        raise AIServiceUnavailableError(
            "AI returned incomplete or invalid JSON. Try again with fewer questions.",
            detail=str(last_exc) if last_exc else last_raw[:500],
            retryable=True,
        )


class GeminiExplanationGenerator(ExplanationGenerator):
    def generate(self, question) -> dict:
        system, user_prompt, max_tokens = build_explanation_generation_prompt(question)
        token_budgets = [max_tokens, min(max_tokens * 2, 4096)]
        last_raw = ""
        last_exc: json.JSONDecodeError | TypeError | None = None

        for budget in token_budgets:
            result = gemini_client.chat_with_fallback(
                user_prompt,
                system=system,
                max_output_tokens=budget,
                json_mode=True,
            )
            last_raw = result.text
            try:
                data = _parse_explanation_json(last_raw)
                if data.get("explanation_steps") or data.get("solution_summary"):
                    return data
            except (json.JSONDecodeError, TypeError) as exc:
                last_exc = exc
                logger.warning(
                    "Failed to parse Gemini explanation JSON (budget=%s): %s",
                    budget,
                    exc,
                )

        raise AIServiceUnavailableError(
            "AI returned incomplete explanation JSON. Please try again.",
            detail=str(last_exc) if last_exc else last_raw[:500],
            retryable=True,
        )


class GeminiQuestionValidator(QuestionValidator):
    def validate(self, stem, choices, topic, difficulty, correct_label=""):
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
            logger.warning("Failed to parse Gemini validation JSON: %s", exc)
        return stub.validate(stem, choices, topic, difficulty, correct_label)


class GeminiAdaptiveFeedbackGenerator(AdaptiveFeedbackGenerator):
    def generate(
        self,
        topic: str,
        question: str,
        user_answer: str,
        correct_answer: str,
        confidence: str = "medium",
        question_type: str = "",
    ) -> str:
        stub = StubAdaptiveFeedbackGenerator()
        system, prompt = build_adaptive_feedback_prompt(
            topic,
            question,
            user_answer,
            correct_answer,
            confidence,
            question_type=question_type,
        )
        result = _chat(
            prompt, system=system, max_output_tokens=adaptive_feedback_max_tokens()
        )
        return result or stub.generate(
            topic,
            question,
            user_answer,
            correct_answer,
            confidence,
            question_type=question_type,
        )


class GeminiErrorClassifier(ErrorClassifier):
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

"""OpenAI-backed AI service implementations."""

import json
import logging
import re

from django.conf import settings

from apps.ai.helpers import calibration_narrative_from_matrix, course_review_narrative
from apps.ai.prompts import (
    build_calibration_prompt,
    build_course_report_prompt,
    build_difficulty_tag_prompt,
    build_question_generation_prompt,
    build_question_validation_prompt,
)
from apps.ai.interfaces import (
    CalibrationAnalyzer,
    CurriculumAdvisor,
    DifficultyTagger,
    ErrorClassifier,
    QuestionGenerator,
    QuestionValidator,
)
from apps.ai.stubs import (
    StubCalibrationAnalyzer,
    StubCurriculumAdvisor,
    StubDifficultyTagger,
    StubErrorClassifier,
    StubQuestionGenerator,
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


def _chat(prompt: str, system: str = "You are a concise educational analytics assistant.") -> str | None:
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
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
    def generate(self, topic, difficulty: str, count: int = 5, reference_stem: str = ""):
        if topic is None:
            return StubQuestionGenerator().generate(topic, difficulty, count, reference_stem)
        system, user_prompt, _max_tokens = build_question_generation_prompt(
            topic, difficulty, count, reference_stem
        )
        raw = _chat(user_prompt, system=system)
        if not raw:
            return StubQuestionGenerator().generate(topic, difficulty, count, reference_stem)
        try:
            cleaned = raw
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                cleaned = match.group(0)
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data[:count]
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to parse question generation JSON: %s", exc)
        return []


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
        raw = _chat(prompt, system=system)
        if not raw:
            return stub.validate(stem, choices, topic, difficulty, correct_label)
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to parse validation JSON: %s", exc)
        return stub.validate(stem, choices, topic, difficulty, correct_label)


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

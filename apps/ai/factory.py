"""Factory for AI services — OpenAI/Gemini/Ollama when enabled, stubs otherwise."""

import logging

from django.conf import settings

from apps.ai.interfaces import (
    AdaptiveFeedbackGenerator,
    CalibrationAnalyzer,
    CurriculumAdvisor,
    DifficultyTagger,
    ErrorClassifier,
    QuestionGenerator,
    QuestionValidator,
    SpacedRepetitionScheduler,
    TutorEngine,
)
from apps.ai.stubs import (
    RuleBasedSpacedRepetitionScheduler,
    StubAdaptiveFeedbackGenerator,
    StubCalibrationAnalyzer,
    StubCurriculumAdvisor,
    StubDifficultyTagger,
    StubErrorClassifier,
    StubQuestionGenerator,
    StubQuestionValidator,
    StubTutorEngine,
)

logger = logging.getLogger(__name__)


def _ai_available() -> bool:
    if not settings.AI_ENABLED:
        return False
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY)
    if provider == "ollama":
        from apps.ai.providers.ollama_client import is_cloud_host

        if is_cloud_host():
            return bool(getattr(settings, "OLLAMA_API_KEY", ""))
        return True
    return bool(settings.OPENAI_API_KEY)


def is_ai_configured() -> bool:
    """Whether AI is enabled and the active provider has required credentials."""
    return _ai_available()


def get_ai_provider_label() -> str:
    """Human-readable label for the active AI provider."""
    if not _ai_available():
        return "Off"
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        return "Gemini"
    if provider == "ollama":
        from apps.ai.providers.ollama_client import is_cloud_host

        return "Ollama Cloud" if is_cloud_host() else "Ollama"
    return "OpenAI"


def _ollama_import():
    from apps.ai.providers import ollama_provider

    return ollama_provider


def get_question_generator() -> QuestionGenerator:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiQuestionGenerator

                return GeminiQuestionGenerator()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaQuestionGenerator()
            from apps.ai.providers.openai_provider import OpenAIQuestionGenerator

            return OpenAIQuestionGenerator()
        except Exception as exc:
            logger.warning("Falling back to stub QuestionGenerator: %s", exc)
    return StubQuestionGenerator()


def get_question_validator() -> QuestionValidator:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiQuestionValidator

                return GeminiQuestionValidator()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaQuestionValidator()
            from apps.ai.providers.openai_provider import OpenAIQuestionValidator

            return OpenAIQuestionValidator()
        except Exception as exc:
            logger.warning("Falling back to stub QuestionValidator: %s", exc)
    return StubQuestionValidator()


def get_difficulty_tagger() -> DifficultyTagger:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiDifficultyTagger

                return GeminiDifficultyTagger()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaDifficultyTagger()
            from apps.ai.providers.openai_provider import OpenAIDifficultyTagger

            return OpenAIDifficultyTagger()
        except Exception as exc:
            logger.warning("Falling back to stub DifficultyTagger: %s", exc)
    return StubDifficultyTagger()


def get_calibration_analyzer() -> CalibrationAnalyzer:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiCalibrationAnalyzer

                return GeminiCalibrationAnalyzer()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaCalibrationAnalyzer()
            from apps.ai.providers.openai_provider import OpenAICalibrationAnalyzer

            return OpenAICalibrationAnalyzer()
        except Exception as exc:
            logger.warning("Falling back to stub CalibrationAnalyzer: %s", exc)
    return StubCalibrationAnalyzer()


def get_spaced_repetition_scheduler() -> SpacedRepetitionScheduler:
    return RuleBasedSpacedRepetitionScheduler()


def get_tutor_engine() -> TutorEngine:
    return StubTutorEngine()


def get_error_classifier() -> ErrorClassifier:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiErrorClassifier

                return GeminiErrorClassifier()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaErrorClassifier()
            from apps.ai.providers.openai_provider import OpenAIErrorClassifier

            return OpenAIErrorClassifier()
        except Exception as exc:
            logger.warning("Falling back to stub ErrorClassifier: %s", exc)
    return StubErrorClassifier()


def get_curriculum_advisor() -> CurriculumAdvisor:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiCurriculumAdvisor

                return GeminiCurriculumAdvisor()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaCurriculumAdvisor()
            from apps.ai.providers.openai_provider import OpenAICurriculumAdvisor

            return OpenAICurriculumAdvisor()
        except Exception as exc:
            logger.warning("Falling back to stub CurriculumAdvisor: %s", exc)
    return StubCurriculumAdvisor()


def get_adaptive_feedback_generator() -> AdaptiveFeedbackGenerator:
    if _ai_available():
        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_provider import GeminiAdaptiveFeedbackGenerator

                return GeminiAdaptiveFeedbackGenerator()
            if settings.LLM_PROVIDER == "ollama":
                return _ollama_import().OllamaAdaptiveFeedbackGenerator()
            from apps.ai.providers.openai_provider import OpenAIAdaptiveFeedbackGenerator

            return OpenAIAdaptiveFeedbackGenerator()
        except Exception as exc:
            logger.warning("Falling back to stub AdaptiveFeedbackGenerator: %s", exc)
    return StubAdaptiveFeedbackGenerator()

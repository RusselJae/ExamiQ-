from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.ai.factory import (
    get_ai_provider_label,
    get_calibration_analyzer,
    get_curriculum_advisor,
    get_difficulty_tagger,
    get_error_classifier,
    get_question_generator,
    get_spaced_repetition_scheduler,
)
from apps.ai.stubs import (
    RuleBasedSpacedRepetitionScheduler,
    StubCalibrationAnalyzer,
    StubCurriculumAdvisor,
    StubDifficultyTagger,
    StubErrorClassifier,
    StubQuestionGenerator,
)


@pytest.mark.django_db
class TestAIFactory:
    @override_settings(AI_ENABLED=False, OPENAI_API_KEY="")
    def test_returns_stubs_when_disabled(self):
        assert isinstance(get_question_generator(), StubQuestionGenerator)
        assert isinstance(get_difficulty_tagger(), StubDifficultyTagger)
        assert isinstance(get_calibration_analyzer(), StubCalibrationAnalyzer)
        assert isinstance(get_error_classifier(), StubErrorClassifier)
        assert isinstance(get_curriculum_advisor(), StubCurriculumAdvisor)

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="openai", OPENAI_API_KEY="test-key", OPENAI_MODEL="gpt-4o-mini")
    @patch("apps.ai.providers.openai_provider._chat")
    def test_returns_openai_providers_when_enabled(self, mock_chat):
        from apps.ai.providers.openai_provider import OpenAIDifficultyTagger

        mock_chat.return_value = "medium"
        tagger = get_difficulty_tagger()
        assert isinstance(tagger, OpenAIDifficultyTagger)
        assert tagger.tag("Solve for x", "easy") == "medium"
        mock_chat.assert_called()

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")
    @patch("apps.ai.providers.openai_provider._chat")
    def test_openai_api_failure_falls_back(self, mock_chat):
        mock_chat.return_value = None
        tagger = get_difficulty_tagger()
        assert tagger.tag("Short question", "medium") in {"easy", "medium", "hard"}

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")
    @patch("apps.ai.providers.openai_provider._chat")
    def test_question_generator_parses_json(self, mock_chat, topic):
        mock_chat.return_value = '[{"stem": "New Q?", "choices": [{"label":"A","text":"1","is_correct":true}]}]'
        results = get_question_generator().generate(topic, "easy", 1)
        assert len(results) == 1
        assert results[0]["stem"] == "New Q?"

    @override_settings(AI_ENABLED=False)
    def test_spaced_repetition_uses_rule_based_scheduler(self):
        assert isinstance(get_spaced_repetition_scheduler(), RuleBasedSpacedRepetitionScheduler)

    @override_settings(AI_ENABLED=False)
    def test_ai_provider_label_off_when_disabled(self):
        assert get_ai_provider_label() == "Off"

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    def test_ai_provider_label_gemini(self):
        assert get_ai_provider_label() == "Gemini"

    @override_settings(
        AI_ENABLED=True,
        LLM_PROVIDER="ollama",
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
    )
    def test_ai_provider_label_ollama_cloud(self):
        assert get_ai_provider_label() == "Ollama Cloud"

    @override_settings(
        AI_ENABLED=True,
        LLM_PROVIDER="ollama",
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
    )
    @patch("apps.ai.providers.ollama_provider.ollama_client.chat")
    def test_ollama_difficulty_tagger(self, mock_chat):
        from apps.ai.providers.ollama_provider import OllamaDifficultyTagger

        mock_chat.return_value = "hard"
        tagger = get_difficulty_tagger()
        assert isinstance(tagger, OllamaDifficultyTagger)
        assert tagger.tag("Long complex question", "easy") == "hard"

    @override_settings(
        AI_ENABLED=True,
        LLM_PROVIDER="ollama",
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
    )
    @patch("apps.ai.providers.ollama_provider.ollama_client.chat_with_fallback")
    def test_ollama_question_generator_parses_json(self, mock_chat, topic):
        from apps.ai.providers.ollama_client import ChatResult

        mock_chat.return_value = ChatResult(
            text='[{"stem": "Ollama Q?", "choices": [{"label":"A","text":"1","is_correct":true}]}]',
            model_used="gpt-oss:120b",
        )
        results = get_question_generator().generate(topic, "easy", 1)
        assert len(results) == 1
        assert results[0]["stem"] == "Ollama Q?"

    @override_settings(AI_ENABLED=False, OLLAMA_API_KEY="")
    def test_ollama_off_without_key_on_cloud(self):
        with override_settings(
            AI_ENABLED=True,
            LLM_PROVIDER="ollama",
            OLLAMA_API_KEY="",
            OLLAMA_BASE_URL="https://ollama.com",
        ):
            assert get_ai_provider_label() == "Off"
            assert isinstance(get_question_generator(), StubQuestionGenerator)

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    @patch("apps.ai.providers.gemini_provider.gemini_client.chat")
    def test_gemini_difficulty_tagger(self, mock_chat):
        from apps.ai.providers.gemini_provider import GeminiDifficultyTagger

        mock_chat.return_value = "hard"
        tagger = get_difficulty_tagger()
        assert isinstance(tagger, GeminiDifficultyTagger)
        assert tagger.tag("Long complex question", "easy") == "hard"

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    @patch("apps.ai.providers.gemini_provider.gemini_client.chat_with_fallback")
    def test_gemini_question_generator_parses_json(self, mock_chat, topic):
        from apps.ai.providers.gemini_client import ChatResult

        mock_chat.return_value = ChatResult(
            text='[{"stem": "Gemini Q?", "choices": [{"label":"A","text":"1","is_correct":true}]}]',
            model_used="gemini-1.5-flash",
        )
        results = get_question_generator().generate(topic, "easy", 1)
        assert len(results) == 1
        assert results[0]["stem"] == "Gemini Q?"

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    @patch("apps.ai.providers.gemini_provider.gemini_client.chat_with_fallback")
    def test_gemini_question_generator_raises_on_api_failure(self, mock_chat, topic):
        from apps.ai.exceptions import AIServiceUnavailableError

        mock_chat.side_effect = AIServiceUnavailableError("AI unavailable: API quota exceeded.")
        with pytest.raises(AIServiceUnavailableError):
            get_question_generator().generate(topic, "easy", 2)

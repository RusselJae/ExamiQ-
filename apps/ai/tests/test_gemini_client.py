from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.providers import gemini_client


@pytest.fixture(autouse=True)
def clear_model_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestGeminiClient:
    @override_settings(GEMINI_API_KEY="test-key")
    @patch("apps.ai.providers.gemini_client.urllib.request.urlopen")
    def test_list_available_models_filters_generate_content(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"models": ['
            b'{"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},'
            b'{"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}'
            b"]}"
        )
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        models = gemini_client.list_available_models(force_refresh=True)
        assert models == ["gemini-1.5-flash"]

        cached = gemini_client.list_available_models()
        assert cached == ["gemini-1.5-flash"]
        assert mock_urlopen.call_count == 1

    @override_settings(
        GEMINI_API_KEY="test-key",
        GEMINI_MODEL="gemini-old",
        GEMINI_FALLBACK_MODELS=["gemini-1.5-pro"],
    )
    @patch("apps.ai.providers.gemini_client.list_available_models", return_value=["gemini-2.0-flash", "gemini-1.5-pro"])
    @patch("apps.ai.providers.gemini_client._generate_with_model")
    @patch("apps.ai.providers.gemini_client.time.sleep")
    def test_chat_with_fallback_tries_next_model_on_quota(self, mock_sleep, mock_generate, _mock_list):
        mock_generate.side_effect = [
            Exception("429 You exceeded your current quota"),
            Exception("429 You exceeded your current quota"),
            Exception("429 You exceeded your current quota"),
            "Generated text",
        ]

        result = gemini_client.chat_with_fallback("prompt", system="sys")
        assert result.text == "Generated text"
        assert result.model_used == "gemini-1.5-pro"
        assert mock_generate.call_count == 4

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-1.5-flash")
    @patch(
        "apps.ai.providers.gemini_client.list_available_models",
        return_value=["gemini-2.0-flash", "gemini-2.5-flash"],
    )
    def test_models_to_try_skips_unavailable_configured_models(self, _mock_list):
        models = gemini_client.models_to_try()
        assert models == ["gemini-2.0-flash", "gemini-2.5-flash"]
        assert "gemini-1.5-flash" not in models

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.0-flash")
    @patch("apps.ai.providers.gemini_client.list_available_models", return_value=["gemini-2.0-flash"])
    @patch("apps.ai.providers.gemini_client._generate_with_model", side_effect=Exception("404 not found"))
    def test_chat_with_fallback_skips_404_without_retry(self, mock_generate, _mock_list):
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            gemini_client.chat_with_fallback("prompt")
        assert mock_generate.call_count == 1
        assert exc_info.value.retryable is False

    @override_settings(
        GEMINI_API_KEY="test-key",
        GEMINI_MODEL="gemini-1.5-flash",
        GEMINI_FALLBACK_MODELS=[],
    )
    @patch("apps.ai.providers.gemini_client.list_available_models", return_value=[])
    @patch("apps.ai.providers.gemini_client._generate_with_model")
    @patch("apps.ai.providers.gemini_client.time.sleep")
    def test_chat_with_fallback_retries_before_next_model(self, mock_sleep, mock_generate, _mock_list):
        mock_generate.side_effect = [
            Exception("503 service unavailable"),
            "ok",
        ]

        result = gemini_client.chat_with_fallback("prompt")
        assert result.text == "ok"
        assert mock_generate.call_count == 2
        mock_sleep.assert_called()

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-1.5-flash", GEMINI_FALLBACK_MODELS=[])
    @patch("apps.ai.providers.gemini_client.list_available_models", return_value=[])
    @patch("apps.ai.providers.gemini_client._generate_with_model", side_effect=Exception("429 quota exceeded"))
    @patch("apps.ai.providers.gemini_client.time.sleep")
    def test_chat_with_fallback_raises_when_all_fail(self, _mock_sleep, _mock_generate, _mock_list):
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            gemini_client.chat_with_fallback("prompt")
        assert "quota" in exc_info.value.message.lower()
        assert exc_info.value.retryable is True

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.providers import ollama_client


@pytest.fixture(autouse=True)
def clear_model_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestOllamaClient:
    @override_settings(
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_MODEL="gpt-oss:120b",
        OLLAMA_FALLBACK_MODELS=["gpt-oss:20b"],
    )
    @patch("apps.ai.providers.ollama_client.urllib.request.urlopen")
    def test_chat_with_fallback_parses_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"message": {"role": "assistant", "content": "Hello from cloud"}}'
        )
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = ollama_client.chat_with_fallback("Say hello", system="Be brief")
        assert result.text == "Hello from cloud"
        assert result.model_used == "gpt-oss:120b"

        request = mock_urlopen.call_args[0][0]
        assert request.full_url == "https://ollama.com/api/chat"
        assert request.get_header("Authorization") == "Bearer test-key"

    @override_settings(
        OLLAMA_API_KEY="",
        OLLAMA_BASE_URL="https://ollama.com",
    )
    def test_cloud_requires_api_key(self):
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            ollama_client.chat_with_fallback("hi")
        assert "API key" in exc_info.value.message

    @override_settings(
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_MODEL="missing-model",
        OLLAMA_FALLBACK_MODELS=[],
    )
    @patch("apps.ai.providers.ollama_client.list_available_models", return_value=[])
    @patch("apps.ai.providers.ollama_client._chat_with_model", side_effect=Exception("404 not found"))
    def test_skips_retries_on_404(self, _mock_chat, _mock_list):
        with pytest.raises(AIServiceUnavailableError):
            ollama_client.chat_with_fallback("prompt")
        assert _mock_chat.call_count == 1

    @override_settings(
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_MODEL="gpt-oss:120b",
        OLLAMA_FALLBACK_MODELS=["gpt-oss:20b"],
    )
    @patch("apps.ai.providers.ollama_client.list_available_models", return_value=[])
    @patch("apps.ai.providers.ollama_client._chat_with_model")
    @patch("apps.ai.providers.ollama_client.time.sleep")
    def test_fallback_model_on_failure(self, _mock_sleep, mock_chat, _mock_list):
        mock_chat.side_effect = [
            Exception("503 unavailable"),
            Exception("503 unavailable"),
            Exception("503 unavailable"),
            "ok from fallback",
        ]

        result = ollama_client.chat_with_fallback("prompt")
        assert result.text == "ok from fallback"
        assert result.model_used == "gpt-oss:20b"

    @override_settings(
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
    )
    @patch("apps.ai.providers.ollama_client.urllib.request.urlopen")
    def test_list_available_models(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"models": [{"name": "gpt-oss:120b"}, {"name": "gpt-oss:20b"}]}'
        )
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        models = ollama_client.list_available_models()
        assert models == ["gpt-oss:120b", "gpt-oss:20b"]

    @override_settings(
        OLLAMA_API_KEY="cache-key",
        OLLAMA_BASE_URL="https://ollama.com",
    )
    @patch("apps.ai.providers.ollama_client.urllib.request.urlopen")
    def test_list_available_models_caches(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"models": [{"name": "gpt-oss:120b"}, {"name": "gpt-oss:20b"}]}'
        )
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        models = ollama_client.list_available_models(force_refresh=True)
        assert models == ["gpt-oss:120b", "gpt-oss:20b"]

        cached = ollama_client.list_available_models()
        assert cached == ["gpt-oss:120b", "gpt-oss:20b"]
        assert mock_urlopen.call_count == 1

    @override_settings(
        OLLAMA_API_KEY="test-key",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_MODEL="gpt-oss:120b",
        OLLAMA_FALLBACK_MODELS=["gpt-oss:20b"],
    )
    @patch("apps.ai.providers.ollama_client.list_available_models", return_value=[])
    @patch(
        "apps.ai.providers.ollama_client._chat_with_model",
        side_effect=RuntimeError("HTTP 429: rate limit reached"),
    )
    @patch("apps.ai.providers.ollama_client.time.sleep")
    def test_rate_limit_does_not_try_fallback_models(self, _mock_sleep, mock_chat, _mock_list):
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            ollama_client.chat_with_fallback("prompt")
        assert "rate limit" in exc_info.value.message.lower()
        assert exc_info.value.retryable is True
        assert mock_chat.call_count == 1

    def test_is_cloud_host(self):
        with override_settings(OLLAMA_BASE_URL="https://ollama.com"):
            assert ollama_client.is_cloud_host() is True
        with override_settings(OLLAMA_BASE_URL="http://localhost:11434"):
            assert ollama_client.is_cloud_host() is False

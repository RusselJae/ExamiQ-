"""Shared LLM chat + availability helpers for AI features."""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def ai_available() -> bool:
    """Return whether a usable LLM provider is configured."""
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


def chat(
    prompt: str,
    system: str = "You are a concise educational analytics assistant.",
    max_output_tokens: int = 800,
) -> str | None:
    """Best-effort chat call; returns None instead of raising on failures."""
    provider = settings.LLM_PROVIDER
    try:
        if provider == "gemini":
            from apps.ai.providers import gemini_client

            return gemini_client.chat(
                prompt, system=system, max_output_tokens=max_output_tokens
            )
        if provider == "ollama":
            from apps.ai.providers import ollama_client

            return ollama_client.chat(
                prompt, system=system, max_output_tokens=max_output_tokens
            )
        from apps.ai.providers.openai_provider import _chat as openai_chat

        return openai_chat(prompt, system=system, max_output_tokens=max_output_tokens)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI chat failed (%s): %s", provider, exc)
        return None

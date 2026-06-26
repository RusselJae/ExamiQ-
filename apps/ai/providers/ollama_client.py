"""Ollama API client — defaults to Ollama Cloud (https://ollama.com)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings

from apps.ai.exceptions import AIServiceUnavailableError

logger = logging.getLogger(__name__)

MAX_RETRIES_PER_MODEL = 2
CHAT_TIMEOUT_SECONDS = 120


@dataclass
class ChatResult:
    text: str
    model_used: str


def is_cloud_host() -> bool:
    return "ollama.com" in settings.OLLAMA_BASE_URL.lower()


def _base_url() -> str:
    return settings.OLLAMA_BASE_URL.rstrip("/")


def _api_url(path: str) -> str:
    return f"{_base_url()}{path}"


def _request_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = getattr(settings, "OLLAMA_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _is_retriable(exc: Exception) -> bool:
    text = str(exc).lower()
    if any(token in text for token in ("429", "quota", "rate limit", "too many")):
        return True
    if any(token in text for token in ("500", "502", "503", "504", "unavailable", "timeout")):
        return True
    return False


def _is_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "404" in text or "not found" in text


def list_available_models(*, force_refresh: bool = False) -> list[str]:
    """List models from Ollama /api/tags (best-effort)."""
    if is_cloud_host() and not settings.OLLAMA_API_KEY:
        return []

    request = urllib.request.Request(
        _api_url("/api/tags"),
        headers=_request_headers(),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Failed to list Ollama models: %s", exc)
        return []

    models: list[str] = []
    for item in data.get("models", []):
        name = item.get("name") or item.get("model")
        if name:
            models.append(str(name))
    return models


def models_to_try(primary: str | None = None) -> list[str]:
    primary = primary or settings.OLLAMA_MODEL
    ordered: list[str] = []

    def add(model: str) -> None:
        if model and model not in ordered:
            ordered.append(model)

    discovered = list_available_models()
    if discovered:
        discovered_set = set(discovered)
        if primary in discovered_set:
            add(primary)
        for model in discovered:
            add(model)
        for model in getattr(settings, "OLLAMA_FALLBACK_MODELS", []):
            if model in discovered_set:
                add(model)
        if ordered:
            return ordered

    add(primary)
    for model in getattr(settings, "OLLAMA_FALLBACK_MODELS", []):
        add(model)
    return ordered


def _chat_with_model(
    model_name: str,
    *,
    system: str,
    user_prompt: str,
    max_output_tokens: int,
    json_mode: bool = False,
) -> str:
    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_prompt})

    payload: dict = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": max_output_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _api_url("/api/chat"),
        data=body,
        headers=_request_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=CHAT_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    if data.get("error"):
        raise RuntimeError(str(data["error"]))

    message = data.get("message") or {}
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned empty response")
    return content.strip()


def chat_with_fallback(
    prompt: str,
    *,
    system: str = "You are a concise educational analytics assistant.",
    max_output_tokens: int = 500,
    primary_model: str | None = None,
    json_mode: bool = False,
) -> ChatResult:
    """Call Ollama with per-model retries and model fallback."""
    if is_cloud_host() and not settings.OLLAMA_API_KEY:
        raise AIServiceUnavailableError(
            "Ollama Cloud API key is not configured.",
            detail="OLLAMA_API_KEY missing — create one at https://ollama.com/settings/keys",
        )

    last_error: Exception | None = None
    for model_name in models_to_try(primary_model):
        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                text = _chat_with_model(
                    model_name,
                    system=system,
                    user_prompt=prompt,
                    max_output_tokens=max_output_tokens,
                    json_mode=json_mode,
                )
                logger.info("Ollama success with model %s", model_name)
                return ChatResult(text=text, model_used=model_name)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Ollama model %s attempt %s failed: %s",
                    model_name,
                    attempt + 1,
                    exc,
                )
                if _is_not_found(exc):
                    break
                if attempt < MAX_RETRIES_PER_MODEL and _is_retriable(exc):
                    time.sleep(min(2**attempt, 8))
                    continue
                break

    detail = str(last_error) if last_error else "unknown error"
    raise AIServiceUnavailableError(_user_facing_message(last_error), detail=detail)


def _user_facing_message(exc: Exception | None) -> str:
    if exc is None:
        return "AI service is temporarily unavailable. Please try again later."
    text = str(exc).lower()
    if "401" in text or "403" in text or "unauthorized" in text:
        return (
            "AI unavailable: invalid or missing Ollama API key. "
            "Create one at ollama.com/settings/keys."
        )
    if "429" in text or "rate limit" in text or "quota" in text:
        return "AI unavailable: Ollama rate limit reached. Try again later."
    if "404" in text or "not found" in text:
        return (
            "AI unavailable: configured Ollama model was not found. "
            "Update OLLAMA_MODEL in .env or check https://ollama.com/search?c=cloud"
        )
    if "connection" in text or "refused" in text:
        return (
            "AI unavailable: cannot reach Ollama. "
            "For cloud, set OLLAMA_BASE_URL=https://ollama.com and OLLAMA_API_KEY."
        )
    return "AI service is temporarily unavailable. Please try again later."


def chat(
    prompt: str,
    *,
    system: str = "You are a concise educational analytics assistant.",
    max_output_tokens: int = 500,
) -> str | None:
    """Best-effort chat for non-critical features; returns None on failure."""
    try:
        return chat_with_fallback(
            prompt,
            system=system,
            max_output_tokens=max_output_tokens,
        ).text
    except AIServiceUnavailableError as exc:
        logger.warning("Ollama chat failed: %s", exc.detail or exc.message)
        return None

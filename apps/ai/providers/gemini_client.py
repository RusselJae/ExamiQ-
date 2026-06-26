"""Gemini API client with model discovery, retry, and fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from apps.ai.exceptions import AIServiceUnavailableError

logger = logging.getLogger(__name__)

MODELS_LIST_URL = "https://generativelanguage.googleapis.com/v1/models"
CACHE_TTL_SECONDS = 3600
MAX_RETRIES_PER_MODEL = 2
# Image/multimodal-only models — skip for text MCQ generation.
EXCLUDED_MODEL_MARKERS = ("-image", "gemma-")


def _is_text_generation_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return not any(marker in lowered for marker in EXCLUDED_MODEL_MARKERS)


def _is_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "404" in text or "not found" in text


@dataclass
class ChatResult:
    text: str
    model_used: str


def _cache_key() -> str:
    key_hash = hashlib.md5(settings.GEMINI_API_KEY.encode()).hexdigest()[:12]
    return f"gemini_models_{key_hash}"


def _is_retriable(exc: Exception) -> bool:
    text = str(exc).lower()
    if any(token in text for token in ("429", "quota", "resource exhausted", "rate limit")):
        return True
    if any(token in text for token in ("500", "502", "503", "504", "overloaded", "unavailable")):
        return True
    return False


def _parse_retry_delay(exc: Exception) -> float | None:
    match = re.search(r"retry in ([\d.]+)s", str(exc), re.IGNORECASE)
    if match:
        return min(float(match.group(1)), 30.0)
    return None


def list_available_models(*, force_refresh: bool = False) -> list[str]:
    """List Gemini models that support generateContent (cached 1 hour)."""
    if not settings.GEMINI_API_KEY:
        return []

    cache_key = _cache_key()
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached:
            return cached

    url = f"{MODELS_LIST_URL}?key={settings.GEMINI_API_KEY}"
    request = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Failed to list Gemini models: %s", exc)
        return []

    models: list[str] = []
    for item in data.get("models", []):
        name = str(item.get("name", "")).replace("models/", "")
        methods = item.get("supportedGenerationMethods", [])
        if name and "generateContent" in methods and _is_text_generation_model(name):
            models.append(name)

    if models:
        cache.set(cache_key, models, CACHE_TTL_SECONDS)
        logger.info("Discovered Gemini models: %s", ", ".join(models))
    return models


def models_to_try(primary: str | None = None) -> list[str]:
    """Build ordered model list, preferring API-discovered models when available."""
    primary = primary or settings.GEMINI_MODEL
    discovered = list_available_models()
    ordered: list[str] = []

    def add(model: str) -> None:
        if model and model not in ordered:
            ordered.append(model)

    if discovered:
        discovered_set = set(discovered)
        if primary in discovered_set:
            add(primary)
        for model in discovered:
            add(model)
        for model in getattr(settings, "GEMINI_FALLBACK_MODELS", []):
            if model in discovered_set:
                add(model)
        return ordered

    add(primary)
    for model in getattr(settings, "GEMINI_FALLBACK_MODELS", []):
        add(model)
    return ordered


def _generate_with_model(
    model_name: str,
    prompt: str,
    *,
    system: str,
    max_output_tokens: int,
    json_mode: bool = False,
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name)
    generation_config: dict = {
        "temperature": 0.3,
        "max_output_tokens": max_output_tokens,
    }
    if json_mode:
        generation_config["response_mime_type"] = "application/json"
    response = model.generate_content(
        f"{system}\n\n{prompt}",
        generation_config=generation_config,
    )
    return response.text.strip()


def chat_with_fallback(
    prompt: str,
    *,
    system: str = "You are a concise educational analytics assistant.",
    max_output_tokens: int = 500,
    primary_model: str | None = None,
    json_mode: bool = False,
) -> ChatResult:
    """Call Gemini with per-model retries and model fallback."""
    if not settings.GEMINI_API_KEY:
        raise AIServiceUnavailableError(
            "Gemini API key is not configured.",
            detail="GEMINI_API_KEY missing",
        )

    last_error: Exception | None = None
    for model_name in models_to_try(primary_model):
        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                text = _generate_with_model(
                    model_name,
                    prompt,
                    system=system,
                    max_output_tokens=max_output_tokens,
                    json_mode=json_mode,
                )
                if text:
                    logger.info("Gemini success with model %s", model_name)
                    return ChatResult(text=text, model_used=model_name)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Gemini model %s attempt %s failed: %s",
                    model_name,
                    attempt + 1,
                    exc,
                )
                if _is_not_found(exc):
                    break
                if attempt < MAX_RETRIES_PER_MODEL and _is_retriable(exc):
                    delay = _parse_retry_delay(exc) or min(2**attempt, 8)
                    time.sleep(delay)
                    continue
                break

    detail = str(last_error) if last_error else "unknown error"
    user_message = _user_facing_message(last_error)
    raise AIServiceUnavailableError(user_message, detail=detail)


def _user_facing_message(exc: Exception | None) -> str:
    if exc is None:
        return "AI service is temporarily unavailable. Please try again later."
    text = str(exc).lower()
    if "quota" in text or "429" in text or "insufficient" in text:
        return (
            "AI unavailable: API quota exceeded. Check your Gemini billing and "
            "plan, or try again later."
        )
    if "api key" in text or "invalid" in text and "key" in text:
        return "AI unavailable: invalid or missing Gemini API key."
    if "not found" in text or "404" in text:
        return (
            "AI unavailable: configured Gemini model is not available for your API key. "
            "Update GEMINI_MODEL in .env or check Google AI Studio."
        )
    return "AI service is temporarily unavailable. Please try again later."


def chat(prompt: str, *, system: str = "You are a concise educational analytics assistant.", max_output_tokens: int = 500) -> str | None:
    """Best-effort chat for non-critical features; returns None on failure."""
    try:
        return chat_with_fallback(prompt, system=system, max_output_tokens=max_output_tokens).text
    except AIServiceUnavailableError as exc:
        logger.warning("Gemini chat failed: %s", exc.detail or exc.message)
        return None

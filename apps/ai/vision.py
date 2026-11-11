"""Vision-model OCR fallback for uploaded images.

Tesseract is optional in this project. When the binary is missing (common on
hosted deployments), an image COR can still be read by the configured
multimodal LLM provider. The model only transcribes text — the same
deterministic matching pipeline then handles the rest.
"""

from __future__ import annotations

import base64
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

VISION_PROMPT = (
    "Transcribe every readable line of text from this Certificate of "
    "Registration image exactly as printed. Preserve table rows, course "
    "codes, and course descriptions. Do not summarize, translate, or invent "
    "values. Return plain text only."
)
VISION_SYSTEM = (
    "You are an OCR assistant. Reproduce the document text faithfully and "
    "never add information that is not visible in the image."
)


def extract_text_from_image(raw: bytes, mime_type: str = "image/jpeg") -> str:
    """Best-effort transcription of an image using the configured AI provider.

    Returns an empty string when AI is disabled or no provider can read
    images. Never raises: OCR failure must not break the signup page.
    """
    if not raw or not settings.AI_ENABLED:
        return ""
    provider = (settings.LLM_PROVIDER or "").lower()
    try:
        if provider == "gemini":
            return _gemini_image_text(raw, mime_type)
        if provider == "openai":
            return _openai_image_text(raw, mime_type)
    except Exception as exc:  # noqa: BLE001 - OCR fallback must not 500
        logger.warning("Vision OCR fallback failed (%s): %s", provider, exc)
    return ""


def _gemini_image_text(raw: bytes, mime_type: str) -> str:
    if not settings.GEMINI_API_KEY:
        return ""
    from google import genai
    from google.genai import types

    from apps.ai.providers.gemini_client import models_to_try

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    contents = [
        VISION_PROMPT,
        types.Part.from_bytes(data=raw, mime_type=mime_type or "image/jpeg"),
    ]
    last_error: Exception | None = None
    for model_name in models_to_try():
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                    system_instruction=VISION_SYSTEM,
                ),
            )
            text = (getattr(response, "text", None) or "").strip()
            if text:
                logger.info("Vision OCR succeeded with %s", model_name)
                return text
        except Exception as exc:  # noqa: BLE001 - try the next model
            last_error = exc
            logger.warning("Gemini vision OCR failed on %s: %s", model_name, exc)
    if last_error is not None:
        raise last_error
    return ""


def _openai_image_text(raw: bytes, mime_type: str) -> str:
    if not settings.OPENAI_API_KEY:
        return ""
    from openai import OpenAI

    encoded = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime_type or 'image/jpeg'};base64,{encoded}"
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    return (response.choices[0].message.content or "").strip()

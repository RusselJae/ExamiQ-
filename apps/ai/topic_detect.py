"""Detect math topics/branches from uploaded learning material."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.ai.chat import ai_available, chat
from apps.ai.prompts import build_topic_detection_prompt

logger = logging.getLogger(__name__)


def detect_topics_from_material(
    source_material: str,
    existing_topics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return detected topics, best existing match, and new-topic suggestions."""
    existing = [
        {"id": int(t["id"]), "name": str(t["name"])}
        for t in existing_topics
        if t.get("id") is not None and t.get("name")
    ]
    stub = _stub_detect(source_material, existing)
    if not ai_available():
        return stub

    system, user = build_topic_detection_prompt(source_material, existing)
    raw = chat(user, system=system, max_output_tokens=800)
    if not raw:
        return stub
    parsed = _parse_detection_json(raw)
    if not parsed:
        return stub
    return _normalize_result(parsed, existing, stub)


def _parse_detection_json(raw: str) -> dict[str, Any] | None:
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse topic detection JSON: %s", exc)
        return None


def _normalize_result(
    parsed: dict[str, Any],
    existing: list[dict[str, Any]],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    detected = parsed.get("detected_topics") or []
    if not isinstance(detected, list):
        detected = fallback["detected_topics"]
    detected_topics = [str(item).strip() for item in detected if str(item).strip()][:8]

    by_id = {t["id"]: t["name"] for t in existing}
    by_name = {t["name"].strip().lower(): t for t in existing}

    matched_id = parsed.get("matched_topic_id")
    matched_name = str(parsed.get("matched_topic_name") or "").strip()
    if matched_id is not None:
        try:
            matched_id = int(matched_id)
        except (TypeError, ValueError):
            matched_id = None
    if matched_id is not None and matched_id not in by_id:
        matched_id = None
    if matched_id is None and matched_name:
        hit = by_name.get(matched_name.lower())
        if hit:
            matched_id = hit["id"]
            matched_name = hit["name"]
    if matched_id is not None:
        matched_name = by_id[matched_id]
    elif not matched_name and fallback.get("matched_topic_id"):
        matched_id = fallback["matched_topic_id"]
        matched_name = fallback["matched_topic_name"]

    suggested = parsed.get("suggested_new_topics") or []
    if not isinstance(suggested, list):
        suggested = fallback["suggested_new_topics"]
    suggested_new = []
    for item in suggested:
        name = str(item).strip()
        if not name:
            continue
        if name.lower() in by_name:
            continue
        if name not in suggested_new:
            suggested_new.append(name)
        if len(suggested_new) >= 5:
            break

    if not detected_topics:
        detected_topics = fallback["detected_topics"]

    return {
        "detected_topics": detected_topics,
        "matched_topic_id": matched_id,
        "matched_topic_name": matched_name or "",
        "suggested_new_topics": suggested_new,
    }


def _stub_detect(
    source_material: str,
    existing: list[dict[str, Any]],
) -> dict[str, Any]:
    text = (source_material or "").lower()
    detected: list[str] = []
    matched_id = None
    matched_name = ""
    best_score = 0
    for topic in existing:
        name = topic["name"]
        tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) > 2]
        score = sum(1 for token in tokens if token in text)
        if score and name not in detected:
            detected.append(name)
        if score > best_score:
            best_score = score
            matched_id = topic["id"]
            matched_name = name

    if not detected and existing:
        matched_id = existing[0]["id"]
        matched_name = existing[0]["name"]
        detected = [matched_name]

    suggested: list[str] = []
    for label in (
        "Algebra",
        "Geometry",
        "Trigonometry",
        "Functions",
        "Statistics",
        "Calculus",
    ):
        if label.lower() in text and not any(
            label.lower() == t["name"].lower() for t in existing
        ):
            suggested.append(label)

    return {
        "detected_topics": detected[:8],
        "matched_topic_id": matched_id,
        "matched_topic_name": matched_name,
        "suggested_new_topics": suggested[:5],
    }

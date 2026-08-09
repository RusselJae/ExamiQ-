"""Score uploaded learning material against a course subject."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.ai.chat import ai_available, chat
from apps.ai.prompts import build_subject_relevance_prompt

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _stub_relevance(source_material: str, subject, topics) -> dict[str, Any]:
    """Keyword-based relevance used when the LLM is unavailable or fails.

    Partial/truncated extracts are fine as long as a subject or topic signal
    appears.
    """
    text = (source_material or "").strip()
    if not text:
        return {
            "related": False,
            "matched_topic_id": None,
            "subject_score": 0,
            "topic_score": 0,
            "reason": "No readable text in the uploaded file.",
        }

    lowered = text.lower()
    material_tokens = _tokenize(lowered)
    code = (getattr(subject, "code", "") or "").strip().lower()
    name = (getattr(subject, "name", "") or "").strip().lower()
    subject_tokens = _tokenize(f"{code} {name}")

    subject_score = 0
    if code and len(code) >= 2 and code in lowered:
        subject_score += 3
    if name and len(name) >= 4 and name in lowered:
        subject_score += 3
    subject_score += sum(1 for token in subject_tokens if token in material_tokens)

    best_topic = None
    best_score = 0
    for topic in topics or []:
        tname = (getattr(topic, "name", "") or "").strip()
        if not tname:
            continue
        score = sum(1 for token in _tokenize(tname) if token in material_tokens)
        t_lower = tname.lower()
        if len(t_lower) >= 4 and t_lower in lowered:
            score += 2
        if score > best_score:
            best_score = score
            best_topic = topic

    related = subject_score >= 1 or best_score >= 1
    if not related:
        return {
            "related": False,
            "matched_topic_id": None,
            "subject_score": subject_score,
            "topic_score": best_score,
            "reason": (
                "This module does not look related to "
                f"{getattr(subject, 'code', '')} — {getattr(subject, 'name', 'this course subject')}."
            ),
        }

    return {
        "related": True,
        "matched_topic_id": best_topic.pk if best_topic else None,
        "subject_score": subject_score,
        "topic_score": best_score,
        "reason": "",
    }


def _parse_relevance_json(raw: str) -> dict[str, Any] | None:
    try:
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse subject relevance JSON: %s", exc)
        return None


def assess_subject_relevance(
    source_material: str,
    subject,
    topics,
    *,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Return whether material looks related to the course subject.

    Uses the LLM for a semantic verdict when AI is configured and available,
    falling back to keyword scoring otherwise. The LLM verdict is authoritative
    because keyword scoring misses scans and docs that never spell out the
    subject code.
    """
    stub = _stub_relevance(source_material, subject, topics)
    if not use_ai or not ai_available():
        return stub

    topic_payload = [
        {"id": t.pk, "name": getattr(t, "name", "") or ""}
        for t in (topics or [])
        if getattr(t, "pk", None) is not None
    ]
    system, user = build_subject_relevance_prompt(
        source_material,
        getattr(subject, "code", "") or "",
        getattr(subject, "name", "") or "",
        topic_payload,
    )
    raw = chat(user, system=system, max_output_tokens=500)
    parsed = _parse_relevance_json(raw)
    if parsed is None:
        return stub

    related = bool(parsed.get("related"))
    reason = str(parsed.get("reason") or "").strip()
    matched_topic = None
    matched_id = parsed.get("matched_topic_id")
    if matched_id is not None:
        try:
            matched_id = int(matched_id)
        except (TypeError, ValueError):
            matched_id = None
        matched_topic = next((t for t in (topics or []) if t.pk == matched_id), None)

    if not related:
        return {
            "related": False,
            "matched_topic_id": None,
            "subject_score": stub["subject_score"],
            "topic_score": stub["topic_score"],
            "reason": reason or stub["reason"],
            "ai_assessed": True,
        }

    if matched_topic is None and stub["matched_topic_id"] is not None:
        matched_topic = next(
            (t for t in (topics or []) if t.pk == stub["matched_topic_id"]), None
        )

    return {
        "related": True,
        "matched_topic_id": matched_topic.pk if matched_topic else None,
        "subject_score": stub["subject_score"],
        "topic_score": stub["topic_score"],
        "reason": reason,
        "ai_assessed": True,
    }

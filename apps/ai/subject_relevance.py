"""Score uploaded learning material against a course subject."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.ai.chat import ai_available, chat
from apps.ai.prompts import build_subject_relevance_prompt

logger = logging.getLogger(__name__)

# Tokens that appear across many math subjects — never enough alone to pass.
_GENERIC_MATH_TOKENS = frozenset(
    {
        "math",
        "maths",
        "mathematics",
        "mathematical",
        "algebra",
        "number",
        "numbers",
        "system",
        "systems",
        "equation",
        "equations",
        "problem",
        "problems",
        "module",
        "lesson",
        "chapter",
        "unit",
        "review",
        "introduction",
        "history",
        "historical",
        "basic",
        "basics",
        "elementary",
        "advanced",
        "course",
        "subject",
        "topic",
        "topics",
        "learning",
        "student",
        "students",
        "teacher",
        "education",
        "example",
        "examples",
        "exercise",
        "exercises",
        "practice",
        "answer",
        "answers",
        "question",
        "questions",
        "solve",
        "solution",
        "solutions",
        "formula",
        "formulas",
        "formulae",
        "concept",
        "concepts",
        "theory",
        "theories",
    }
)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 3}


def _content_tokens(tokens: set[str]) -> set[str]:
    """Drop generic math/education tokens from a token set."""
    return {t for t in tokens if t not in _GENERIC_MATH_TOKENS}


def _stub_relevance(source_material: str, subject, topics) -> dict[str, Any]:
    """Keyword-based relevance used when the LLM is unavailable or fails.

    Requires a strong subject or topic signal so adjacent math subjects
    (e.g. history of mathematics vs plane geometry) do not pass.
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
    material_content = _content_tokens(material_tokens)
    code = (getattr(subject, "code", "") or "").strip().lower()
    name = (getattr(subject, "name", "") or "").strip().lower()
    subject_tokens = _content_tokens(_tokenize(f"{code} {name}"))

    subject_score = 0
    if code and len(code) >= 2 and code in lowered:
        subject_score += 4
    if name and len(name) >= 6 and name in lowered:
        subject_score += 4
    subject_score += sum(2 for token in subject_tokens if token in material_content)

    best_topic = None
    best_score = 0
    for topic in topics or []:
        tname = (getattr(topic, "name", "") or "").strip()
        if not tname:
            continue
        topic_tokens = _content_tokens(_tokenize(tname))
        score = sum(2 for token in topic_tokens if token in material_content)
        t_lower = tname.lower()
        if len(t_lower) >= 6 and t_lower in lowered:
            score += 3
        if score > best_score:
            best_score = score
            best_topic = topic

    # Pass if the subject code/name appears, or at least one distinctive
    # topic/subject token matches. Since garbage PDF syntax is now blocked
    # before reaching this point, we can trust that the text is real content.
    related = subject_score >= 2 or best_score >= 2
    if not related:
        return {
            "related": False,
            "matched_topic_id": None,
            "subject_score": subject_score,
            "topic_score": best_score,
            "reason": (
                "This module does not look related to "
                f"{getattr(subject, 'code', '')} — "
                f"{getattr(subject, 'name', 'this course subject')}. "
                "Upload material that matches this subject."
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


def assess_question_subject_relevance(
    stem: str,
    subject,
    topic=None,
    *,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Return whether a question stem fits the target course subject."""
    from apps.ai.prompts import build_question_subject_relevance_prompt

    text = (stem or "").strip()
    if not text:
        code = getattr(subject, "code", "") or ""
        name = getattr(subject, "name", "") or "this course subject"
        return {
            "related": False,
            "reason": f"Add a question stem for {code} — {name}.",
            "subject_score": 0,
            "topic_score": 0,
        }

    topics = [topic] if topic is not None else []
    stub = _stub_relevance(text, subject, topics)
    if not use_ai or not ai_available():
        return stub

    topic_name = getattr(topic, "name", "") if topic is not None else ""
    system, user = build_question_subject_relevance_prompt(
        text,
        getattr(subject, "code", "") or "",
        getattr(subject, "name", "") or "",
        topic_name,
    )
    raw = chat(user, system=system, max_output_tokens=400)
    parsed = _parse_relevance_json(raw)
    if parsed is None:
        return stub

    related = bool(parsed.get("related"))
    reason = str(parsed.get("reason") or "").strip()
    if not related:
        if not reason:
            code = getattr(subject, "code", "") or ""
            name = getattr(subject, "name", "") or "this course subject"
            reason = (
                f"This question does not look related to {code} — {name}. "
                "Write a stem that matches this subject."
            )
        return {
            "related": False,
            "reason": reason,
            "subject_score": stub["subject_score"],
            "topic_score": stub["topic_score"],
            "ai_assessed": True,
        }

    return {
        "related": True,
        "reason": reason,
        "subject_score": stub["subject_score"],
        "topic_score": stub["topic_score"],
        "ai_assessed": True,
    }

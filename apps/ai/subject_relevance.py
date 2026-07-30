"""Score uploaded learning material against a course subject."""

from __future__ import annotations

import re
from typing import Any


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}


def assess_subject_relevance(
    source_material: str,
    subject,
    topics,
) -> dict[str, Any]:
    """Return whether material looks related to the course subject.

    Uses subject code/name and topic names. Partial/truncated extracts are fine
    as long as a subject or topic signal appears.
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

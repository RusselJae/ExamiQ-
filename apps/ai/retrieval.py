"""Topic-scoped retrieval over stored learning chunks."""

from __future__ import annotations

import re
from typing import Any

from apps.ai.models import LearningChunk, LearningDocument
from apps.ai.source_extract import MAX_PROMPT_CHARS


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}


def score_chunk(text: str, query_tokens: set[str]) -> int:
    if not query_tokens:
        return 0
    chunk_tokens = _tokenize(text)
    return sum(1 for token in query_tokens if token in chunk_tokens)


def retrieve_material_for_topic(
    *,
    document: LearningDocument | None,
    topic,
    max_chars: int = MAX_PROMPT_CHARS,
    limit_chunks: int = 24,
) -> str:
    """Return concatenated top chunks for a topic, capped for the LLM prompt."""
    if document is None:
        return ""
    chunks = list(
        LearningChunk.objects.filter(document=document).order_by("order")[:500]
    )
    if not chunks:
        return ""

    query_parts = [getattr(topic, "name", "") or ""]
    subject = getattr(topic, "subject", None)
    if subject is not None:
        query_parts.append(getattr(subject, "name", "") or "")
        query_parts.append(getattr(subject, "code", "") or "")
    query_tokens = _tokenize(" ".join(query_parts))

    scored: list[tuple[int, Any]] = []
    for chunk in chunks:
        scored.append((score_chunk(chunk.text, query_tokens), chunk))
    scored.sort(key=lambda item: (-item[0], item[1].order))

    # Prefer matched chunks; fall back to early document coverage.
    selected = [c for score, c in scored if score > 0][:limit_chunks]
    if not selected:
        selected = [c for _, c in scored[: min(8, len(scored))]]

    selected.sort(key=lambda c: c.order)
    parts: list[str] = []
    total = 0
    for chunk in selected:
        piece = chunk.text.strip()
        if not piece:
            continue
        if total + len(piece) + 1 > max_chars:
            remain = max_chars - total - 1
            if remain > 80:
                parts.append(piece[:remain])
            break
        parts.append(piece)
        total += len(piece) + 1
    return "\n\n".join(parts)


def sample_material_for_detection(
    document: LearningDocument | None,
    *,
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    """Stratified sample across the document for topic detection."""
    if document is None:
        return ""
    chunks = list(LearningChunk.objects.filter(document=document).order_by("order"))
    if not chunks:
        return ""
    if len(chunks) <= 12:
        selected = chunks
    else:
        step = max(1, len(chunks) // 12)
        selected = chunks[::step][:12]
    parts: list[str] = []
    total = 0
    for chunk in selected:
        piece = chunk.text.strip()
        if not piece:
            continue
        if total + len(piece) + 1 > max_chars:
            break
        parts.append(piece)
        total += len(piece) + 1
    return "\n\n".join(parts)


def sample_material_for_relevance(
    document: LearningDocument | None,
    *,
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    """Front-loaded + stratified sample for subject relevance checks.

    The first chunks usually carry the title/subject identity, while a
    stratified sweep covers the rest of a long document where the subject
    signal may live. This matters for scanned or image-first modules whose
    cover page never produced text.
    """
    if document is None:
        return ""
    chunks = list(LearningChunk.objects.filter(document=document).order_by("order"))
    if not chunks:
        return ""

    head_count = min(6, len(chunks))
    head = chunks[:head_count]
    tail = chunks[head_count:]
    if len(tail) > 12:
        step = max(1, len(tail) // 12)
        tail = tail[::step][:12]
    selected = head + tail

    parts: list[str] = []
    total = 0
    for chunk in selected:
        piece = chunk.text.strip()
        if not piece:
            continue
        if total + len(piece) + 1 > max_chars:
            break
        parts.append(piece)
        total += len(piece) + 1
    return "\n\n".join(parts)

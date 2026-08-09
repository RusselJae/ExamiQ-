"""Subject relevance checks for Add Questions generation."""

from unittest.mock import patch

import pytest

from apps.ai.subject_relevance import assess_subject_relevance


@pytest.fixture(autouse=True)
def _disable_ai(settings):
    """Keep keyword/stub tests deterministic even when .env enables an LLM."""
    settings.AI_ENABLED = False


class _Fake:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_subject_relevance_matches_code_and_topic():
    subject = _Fake(code="TRIG", name="Trigonometry")
    topics = [_Fake(pk=1, name="Right Triangles"), _Fake(pk=2, name="Sine Cosine")]
    result = assess_subject_relevance(
        "Module for TRIG — Right Triangles and sine ratios.",
        subject,
        topics,
    )
    assert result["related"] is True
    assert result["matched_topic_id"] == 1


def test_subject_relevance_rejects_unrelated_material():
    subject = _Fake(code="TRIG", name="Trigonometry")
    topics = [_Fake(pk=1, name="Right Triangles")]
    result = assess_subject_relevance(
        "Introduction to culinary plating and kitchen safety protocols.",
        subject,
        topics,
    )
    assert result["related"] is False
    assert "not look related" in result["reason"].lower() or "not related" in result["reason"].lower()


def test_subject_relevance_allows_partial_related_extract():
    subject = _Fake(code="STAT", name="Elementary Statistics")
    topics = [_Fake(pk=9, name="Probability")]
    result = assess_subject_relevance(
        "STAT short excerpt… Probability basics only.",
        subject,
        topics,
    )
    assert result["related"] is True


@patch("apps.ai.subject_relevance.ai_available", return_value=True)
@patch(
    "apps.ai.subject_relevance.chat",
    return_value='{"related": true, "matched_topic_id": 2, "reason": "Covers sine and cosine ratios."}',
)
def test_semantic_relevance_uses_llm_verdict(_chat, _available):
    subject = _Fake(code="TRIG", name="Trigonometry")
    topics = [_Fake(pk=1, name="Right Triangles"), _Fake(pk=2, name="Sine Cosine")]
    result = assess_subject_relevance(
        "A scanned module whose text never mentions TRIG.",
        subject,
        topics,
    )
    assert result["related"] is True
    assert result["matched_topic_id"] == 2
    assert result["ai_assessed"] is True
    assert "sine and cosine" in result["reason"]


@patch("apps.ai.subject_relevance.ai_available", return_value=True)
@patch("apps.ai.subject_relevance.chat", return_value="not json at all")
def test_semantic_relevance_falls_back_to_keywords_on_bad_json(_chat, _available):
    subject = _Fake(code="TRIG", name="Trigonometry")
    topics = [_Fake(pk=1, name="Right Triangles")]
    result = assess_subject_relevance(
        "Introduction to culinary plating and kitchen safety protocols.",
        subject,
        topics,
    )
    assert result["related"] is False
    assert "not look related" in result["reason"].lower()


@patch("apps.ai.subject_relevance.ai_available", return_value=True)
@patch(
    "apps.ai.subject_relevance.chat",
    return_value='{"related": false, "matched_topic_id": null, "reason": "No trigonometry content."}',
)
def test_semantic_relevance_can_override_keyword_hit(_chat, _available):
    subject = _Fake(code="TRIG", name="Trigonometry")
    topics = [_Fake(pk=1, name="Right Triangles")]
    result = assess_subject_relevance(
        "The word TRIG appears but the module is actually about cooking.",
        subject,
        topics,
    )
    assert result["related"] is False
    assert result["ai_assessed"] is True

import pytest
from django.test import override_settings

from apps.ai.prompts import (
    build_adaptive_feedback_prompt,
    build_exam_feedback_batch_prompt,
    build_exam_feedback_single_prompt,
    build_question_generation_prompt,
    build_tutor_chat_prompt,
    build_tutor_intro_prompt,
    format_exam_feedback_item,
    off_topic_redirect,
    question_generation_max_tokens,
)


@pytest.mark.django_db
class TestQuestionGenerationPrompt:
    @override_settings(GEMINI_QUESTION_MAX_OUTPUT_TOKENS=2048)
    def test_token_budget_scales_with_count(self, topic):
        _, _, tokens_five = build_question_generation_prompt(topic, "easy", 5)
        _, _, tokens_three = build_question_generation_prompt(topic, "easy", 3)
        assert tokens_five == 1400
        assert tokens_three == 840
        assert tokens_five > tokens_three

    def test_includes_subject_and_topic(self, topic):
        system, user, _ = build_question_generation_prompt(topic, "medium", 2)
        assert "ExamiQ+" in system
        assert topic.name in user
        assert topic.subject.code in user


class TestLegacyTutorPrompts:
    def test_tutor_chat_includes_rules_and_context(self):
        system, user = build_tutor_chat_prompt(
            "algebra",
            "How do I factor x^2 + 5x + 6?",
            history=[{"role": "user", "text": "I'm stuck"}],
            exam_context={"exam_name": "Midterm", "topic": "algebra"},
        )
        assert "ExamiQ+" in system
        assert "Do NOT greet" in user
        assert "Midterm" in user
        assert "I'm stuck" in user

    def test_tutor_intro_format(self):
        _, user = build_tutor_intro_prompt("Calculus")
        assert "Topic:" in user
        assert "Lesson:" in user
        assert "Calculus" in user

    def test_adaptive_feedback_includes_confidence(self):
        system, user = build_adaptive_feedback_prompt(
            "geometry",
            "What is the area of a circle?",
            "B",
            "A",
            confidence="low",
            patterns=["confuses radius and diameter"],
        )
        assert "Confidence Level: low" in user
        assert "confuses radius" in user
        assert "TOPIC RESTRICTION" in system or "topic" in system.lower()


class TestExamFeedbackPrompts:
    def test_batch_prompt_includes_schema(self):
        item = format_exam_feedback_item(
            1,
            question="2+2?",
            user_answer="B",
            correct_answer="A",
            concept_tag="arithmetic",
        )
        system, user, tokens = build_exam_feedback_batch_prompt("algebra", item)
        assert "why_wrong" in user
        assert "overall_recommendations" in user
        assert tokens >= 1200
        assert "ExamiQ+" in system

    def test_single_prompt_token_budget(self):
        _, _, tokens = build_exam_feedback_single_prompt(
            "logic",
            "P implies Q?",
            "A",
            "B",
            confidence="high",
        )
        assert tokens >= 1200


class TestOffTopicRedirect:
    def test_redirects_cross_topic_question(self):
        msg = off_topic_redirect("algebra", "What is the derivative of x^2?")
        assert msg is not None
        assert "Calculus" in msg

    def test_allows_same_topic(self):
        assert off_topic_redirect("calculus", "What is the limit as h approaches 0?") is None


class TestTokenHelpers:
    @override_settings(GEMINI_QUESTION_MAX_OUTPUT_TOKENS=2048)
    def test_question_generation_max_tokens_floor(self):
        assert question_generation_max_tokens(1) == 800

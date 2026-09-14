import pytest
from django.test import override_settings

from apps.ai.prompts import (
    build_adaptive_feedback_prompt,
    build_exam_feedback_batch_prompt,
    build_exam_feedback_single_prompt,
    build_explanation_generation_prompt,
    build_question_generation_prompt,
    build_subject_relevance_prompt,
    build_topic_detection_prompt,
    build_tutor_chat_prompt,
    build_tutor_intro_prompt,
    coerce_generate_question_type,
    format_exam_feedback_item,
    off_topic_redirect,
    question_generation_max_tokens,
)
from apps.questions.models import Question


@pytest.mark.django_db
class TestQuestionGenerationPrompt:
    @override_settings(GEMINI_QUESTION_MAX_OUTPUT_TOKENS=2048)
    def test_token_budget_scales_with_count(self, topic):
        _, _, tokens_five = build_question_generation_prompt(topic, "easy", 5)
        _, _, tokens_three = build_question_generation_prompt(topic, "easy", 3)
        assert tokens_five == 1100
        assert tokens_three == 900
        assert tokens_five > tokens_three

    @override_settings(GEMINI_QUESTION_MAX_OUTPUT_TOKENS=2048)
    def test_hard_difficulty_gets_larger_budget(self, topic):
        _, _, hard_tokens = build_question_generation_prompt(topic, "hard", 3)
        _, _, easy_tokens = build_question_generation_prompt(topic, "easy", 3)
        assert hard_tokens > easy_tokens

    def test_includes_subject_and_topic(self, topic):
        system, user, _ = build_question_generation_prompt(topic, "medium", 2)
        assert "ExamiQ+" in system
        assert topic.name in user
        assert topic.subject.code in user
        assert "Year level" in user
        assert topic.subject.year_level.name in user
        assert "omit explanation_steps" in user
        assert "Do NOT include explanation" in system
        assert "randomize" in system.lower() or "correct_label" in system.lower()

    def test_hard_difficulty_includes_advanced_guidance(self, topic):
        _, user, tokens = build_question_generation_prompt(topic, "hard", 3)
        assert "Advanced" in user
        assert "every subject" in user.lower() or "Applies to every subject" in user
        assert tokens > question_generation_max_tokens(3, "medium")

    def test_identification_prompt_mentions_case_insensitive_grading(self, topic):
        system, user, _ = build_question_generation_prompt(
            topic, "medium", 2, question_type=Question.QuestionType.IDENTIFICATION
        )
        assert "identification" in user.lower()
        assert "capitalization" in user.lower() or "capitalization" in system.lower()
        assert "expected_answer" in user

    def test_true_false_prompt_schema(self, topic):
        _, user, _ = build_question_generation_prompt(
            topic, "easy", 1, question_type=Question.QuestionType.TRUE_FALSE
        )
        assert "true or false" in user.lower()
        assert "true_false" in user


class TestLegacyTutorPrompts:
    def test_tutor_chat_includes_rules_and_context(self):
        system, user = build_tutor_chat_prompt(
            "algebra",
            "How do I factor x^2 + 5x + 6?",
            history=[{"role": "user", "text": "I'm stuck"}],
            exam_context={"exam_name": "Midterm", "topic": "algebra"},
            question_context={
                "stem": "Factor x^2 + 5x + 6",
                "user_answer": "B: 5",
                "correct_answer": "A: (x+2)(x+3)",
                "is_correct": False,
            },
        )
        assert "ExamiQ+" in system
        assert "Do NOT greet" in user
        assert "Midterm" in user
        assert "I'm stuck" in user
        assert "TOPIC RESTRICTION" in user
        assert "Factor x^2 + 5x + 6" in user
        assert "unrelated to math" in user.lower() or "outside this topic" in user.lower()
        assert '"steps"' in system or '"steps"' in user
        assert "$...$" in system or "KaTeX" in system

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


class TestSubjectRelevancePrompt:
    def test_includes_subject_and_topics_and_json_schema(self):
        system, user = build_subject_relevance_prompt(
            "Cover page missing… quadratic factoring later in the module.",
            "TRIG",
            "Trigonometry",
            [{"id": 3, "name": "Right Triangles"}],
        )
        assert "ExamiQ+" in system
        assert "PRIMARY" in system or "PRIMARY" in user
        assert "TRIG" in user
        assert "Trigonometry" in user
        assert "Right Triangles" in user
        assert "related" in user
        assert "matched_topic_id" in user
        assert "JSON" in system or "JSON" in user

    def test_truncates_long_excerpts(self):
        long_text = "word " * 13000
        _, user = build_subject_relevance_prompt(long_text, "ALG", "Algebra", [])
        assert "[truncated]" in user


class TestTopicDetectionPrompt:
    def test_includes_existing_topics_and_schema(self):
        system, user = build_topic_detection_prompt(
            "Linear equations module text.",
            [{"id": 1, "name": "Algebra"}],
        )
        assert "ExamiQ+" in system
        assert "Algebra" in user
        assert "detected_topics" in user
        assert "suggested_new_topics" in user


class TestTokenHelpers:
    @override_settings(GEMINI_QUESTION_MAX_OUTPUT_TOKENS=2048)
    def test_question_generation_max_tokens_floor(self):
        assert question_generation_max_tokens(1) == 900

    def test_coerce_generate_question_type_defaults_to_mcq(self):
        assert coerce_generate_question_type(None) == Question.QuestionType.MCQ
        assert coerce_generate_question_type("identification") == Question.QuestionType.IDENTIFICATION


@pytest.mark.django_db
class TestExplanationGenerationPrompt:
    def test_includes_question_and_schema(self, mcq_question):
        question, _correct = mcq_question
        system, user, tokens = build_explanation_generation_prompt(question)
        assert "ExamiQ+" in system
        assert question.stem in user
        assert "explanation_steps" in user
        assert "solution_summary" in user
        assert tokens >= 800
        assert tokens <= 2500
        assert "distractor" in user.lower()

    def test_true_false_prompt_mentions_claim(self, topic):
        question = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.TRUE_FALSE,
            stem="Pi equals exactly 3.",
            expected_answer="False",
            status=Question.Status.APPROVED,
        )
        _, user, _ = build_explanation_generation_prompt(question)
        assert "true" in user.lower() and "false" in user.lower()

    def test_numeric_prompt_mentions_calculation(self, topic):
        question = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.NUMERIC,
            stem="What is 2+2?",
            correct_answer="4",
            status=Question.Status.APPROVED,
        )
        _, user, _ = build_explanation_generation_prompt(question)
        assert "numeric" in user.lower() or "calculation" in user.lower()

    def test_enumeration_prompt_lists_items(self, topic):
        question = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.ENUMERATION,
            stem="Name two types of angles.",
            expected_answer="acute\nobtuse",
            status=Question.Status.APPROVED,
        )
        _, user, _ = build_explanation_generation_prompt(question)
        assert "enumeration" in user.lower() or "each required" in user.lower()

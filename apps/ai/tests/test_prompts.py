import pytest
from django.test import override_settings

from apps.ai.prompts import (
    build_adaptive_feedback_prompt,
    build_concept_practice_question_prompt,
    build_concept_remediation_prompt,
    build_correct_adaptive_feedback_prompt,
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
        assert tokens_five == 3500
        assert tokens_three == 2100
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
        assert "Include explanation_steps" in user
        assert "explanation_steps" in system
        assert "randomize" in system.lower() or "correct_label" in system.lower()

    def test_hard_difficulty_includes_advanced_guidance(self, topic):
        _, user, tokens = build_question_generation_prompt(topic, "hard", 3)
        assert "Advanced" in user
        assert "every subject" in user.lower() or "Applies to every subject" in user
        assert tokens > question_generation_max_tokens(3, "medium")

    def test_non_mcq_generate_type_coerces_to_mcq(self, topic):
        _, user, _ = build_question_generation_prompt(
            topic, "medium", 2, question_type=Question.QuestionType.IDENTIFICATION
        )
        assert "multiple-choice" in user.lower() or "mcq" in user.lower()
        assert "identification" not in user.lower() or "multiple-choice" in user.lower()

    def test_true_false_generate_type_coerces_to_mcq(self, topic):
        _, user, _ = build_question_generation_prompt(
            topic, "easy", 1, question_type=Question.QuestionType.TRUE_FALSE
        )
        assert "true_false" not in user or "multiple-choice" in user.lower()
        assert "choices" in user.lower() or "correct_label" in user.lower()

    def test_exclude_stems_adds_do_not_repeat_block(self, topic):
        _, user, _ = build_question_generation_prompt(
            topic,
            "easy",
            2,
            exclude_stems=["What is 2+2?", "Solve x^2 = 9."],
        )
        assert "### DO NOT REPEAT" in user
        assert "1. What is 2+2?" in user
        assert "2. Solve x^2 = 9." in user
        assert "Create clearly different questions instead." in user
        # No truncation note when the list is under the limit.
        assert "Showing the most recent" not in user

    def test_exclude_stems_truncation_note_shows_at_limit(self, topic):
        stems = [f"Excluded stem {i}" for i in range(40)]
        _, user, _ = build_question_generation_prompt(
            topic, "easy", 2, exclude_stems=stems
        )
        assert "### DO NOT REPEAT" in user
        assert "Showing the most recent 40" in user
        assert "40. Excluded stem 39" in user
        assert "41." not in user

    def test_exclude_stems_block_appears_in_regenerate_branch(self, topic):
        _, user, _ = build_question_generation_prompt(
            topic,
            "easy",
            2,
            reference_stem="Reference stem for improvement.",
            exclude_stems=["Regenerated but deleted again."],
        )
        assert "Regenerate" in user
        assert "### DO NOT REPEAT" in user
        assert "1. Regenerated but deleted again." in user

    def test_no_exclude_stems_omits_do_not_repeat_block(self, topic):
        _, user, _ = build_question_generation_prompt(topic, "easy", 2)
        assert "DO NOT REPEAT" not in user


class TestLegacyTutorPrompts:
    def test_tutor_chat_system_has_new_schema_and_rules(self):
        system, _user = build_tutor_chat_prompt("algebra", "Help me factor x^2 + 5x + 6")
        assert "ExamiQ+" in system
        assert "clear, concise tutor for college math and computer science" in system
        assert "## SCOPE" in system
        assert "## CHOOSE THE REPLY TYPE" in system
        assert "concept_check" in system
        assert '"concept_check"' in system
        assert "## QUALITY RULES" in system
        assert "## TEXT REPLIES" in system
        assert "\\hl" in system
        assert "3-6 steps" in system
        assert "source of truth" in system
        assert "solution: 3-6 steps. concept_check: no steps" in system
        assert "80 words or fewer outside tables" in system
        assert "table block" in system
        assert "exact trap" in system
        assert "portable test" in system
        assert "different content" in system
        assert "Never claim you saved" in system
        assert "Learn more" in system
        assert "8 words or fewer" in system
        assert '"blocks"' in system
        assert '"check"' in system
        assert '"follow_ups"' in system
        assert '"quick_check"' in system
        assert '"remember"' in system
        assert '"table"' in system

    def test_tutor_chat_user_prompt_shape(self):
        _system, user = build_tutor_chat_prompt(
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
        assert "TOPIC RESTRICTION" in user
        assert "Midterm" in user
        assert "I'm stuck" in user
        assert "Student: How do I factor x^2 + 5x + 6?" in user
        assert "Factor x^2 + 5x + 6" in user
        assert "Reply with the JSON object only." in user
        # No subject code in context → the convention rule must be omitted.
        assert "course reference" not in user
        assert "Subject:" not in user

    def test_tutor_chat_convention_rule_follows_subject_code(self):
        _, user = build_tutor_chat_prompt(
            "linear equations",
            "Is a negation a compound statement?",
            question_context={
                "stem": "Which statement is compound?",
                "subject_code": "BSEM 22",
                "subject_name": "College Algebra",
            },
        )
        assert "Subject: BSEM 22 – College Algebra" in user
        assert (
            "Follow the definitions and notation used in the course reference "
            "for BSEM 22" in user
        )
        assert "negation counts as a compound statement" in user
        assert "Reply with the JSON object only." in user

    def test_tutor_chat_choices_rendered_for_mcq(self):
        _, user = build_tutor_chat_prompt(
            "logic",
            "Which option is the correct answer?",
            question_context={
                "stem": "Which statement is compound?",
                "choices": [
                    {"id": "A", "text": "p AND q"},
                    {"id": "B", "text": "not p"},
                ],
                "student_pick": "B",
            },
        )
        assert "Choices:" in user
        assert "A) p AND q" in user
        assert "B) not p" in user
        assert "Student picked: B" in user

    def test_tutor_chat_includes_faculty_steps_for_expansion(self):
        _, user = build_tutor_chat_prompt(
            "algebra",
            "Show the full solution",
            question_context={
                "stem": "Solve 2x + 3 = 11",
                "user_answer": "x = 3",
                "correct_answer": "x = 4",
                "is_correct": False,
                "explanation_steps": [
                    "Subtract 3 from both sides.",
                    "Divide by 2 to get x = 4.",
                ],
                "adaptive_explanation": {
                    "what_went_wrong": "Arithmetic slip when isolating x.",
                    "why": "2x = 8 so x = 4.",
                    "remember": "Undo addition first.",
                },
            },
        )
        assert "Subtract 3 from both sides" in user
        assert "expand these into richer teaching" in user.lower()
        assert "Arithmetic slip" in user
        assert "build on this" in user.lower()
        # The system QUALITY RULES anchor curated content as the source of truth.
        system_text, _user2 = build_tutor_chat_prompt("algebra", "Show the full solution")
        assert "treat them as the source of truth" in system_text


    def test_tutor_intro_format(self):
        _, user = build_tutor_intro_prompt("Calculus")
        assert "Topic:" in user
        assert "Lesson:" in user
        assert "Calculus" in user

    def test_adaptive_feedback_is_structured_json(self):
        system, user = build_adaptive_feedback_prompt(
            "Linear algebra",
            "If matrix A has a determinant of 0, what can be concluded about A?",
            "B: A is non-singular",
            "D: A is singular",
            confidence="high",
            patterns=["confuses singular and non-singular"],
            question_type="Multiple Choice",
            choices=[
                "A: A is invertible",
                "B: A is non-singular",
                "C: A has full rank",
                "D: A is singular",
            ],
            difficulty="Intermediate",
        )
        assert "what_went_wrong" in user
        assert "solution_steps" in user
        assert "GOOD EXAMPLE" in user
        assert "BAD EXAMPLE" in user
        assert "Do not mention confidence" in user or "Do not comment on the student's confidence" in user
        assert "Confidence Level:" not in user
        assert "All options:" in user
        assert "B: A is non-singular" in user
        assert "JSON" in system or "json" in system.lower()
        assert "TOPIC RESTRICTION" in system or "topic" in system.lower()

    def test_correct_adaptive_feedback_prompt(self):
        system, user = build_correct_adaptive_feedback_prompt(
            "Linear algebra",
            "If matrix A has a determinant of 0, what can be concluded about A?",
            "D: A is singular",
            "D: A is singular",
            confidence="high",
            question_type="Multiple Choice",
            choices=[
                "A: A is invertible",
                "B: A is non-singular",
                "C: A has full rank",
                "D: A is singular",
            ],
            difficulty="Intermediate",
        )
        assert "why_it_works" in user
        assert "worked_example" in user
        assert "GOOD EXAMPLE" in user
        assert "Do not mention confidence" in user
        assert "great job" in user.lower()  # in BAD EXAMPLE
        assert "json" in system.lower()


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
        assert question_generation_max_tokens(1) == 1600

    def test_coerce_generate_question_type_defaults_to_mcq(self):
        assert coerce_generate_question_type(None) == Question.QuestionType.MCQ
        assert coerce_generate_question_type("identification") == Question.QuestionType.MCQ
        assert coerce_generate_question_type("true_false") == Question.QuestionType.MCQ
        assert coerce_generate_question_type("mcq") == Question.QuestionType.MCQ


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

    def test_faculty_steps_are_used_as_generation_basis(self, mcq_question):
        from apps.questions.models import ExplanationStep

        question, _correct = mcq_question
        ExplanationStep.objects.create(
            question=question, order=1, content="Faculty step one."
        )
        ExplanationStep.objects.create(
            question=question, order=2, content="Faculty step two."
        )
        _, user, _ = build_explanation_generation_prompt(question)
        assert "Faculty-authored solution steps" in user
        assert "Faculty step one." in user
        assert "Faculty step two." in user

    def test_prompt_has_no_faculty_block_without_steps(self, mcq_question):
        question, _correct = mcq_question
        _, user, _ = build_explanation_generation_prompt(question)
        assert "Faculty-authored solution steps" not in user


class TestConceptReviewPrompts:
    def test_remediation_prompt_includes_inputs(self):
        system, user = build_concept_remediation_prompt(
            concept_name="Solving two-step linear equations",
            subject="College Algebra",
            topic="Linear equations",
            difficulty="beginner",
            miss_count=3,
            missed_questions=[
                {
                    "stem": "Solve 2x+7=15",
                    "chosen_answer": "11",
                    "correct_answer": "4",
                    "confidence": "Sure",
                }
            ],
            previous_feedback_styles=["worked_example"],
            student_stage="second_review",
            preferred_style="mistakes_first",
        )
        assert "ExamiQ+" in system
        assert "Solving two-step linear equations" in user
        assert "worked_example" in user
        assert "mistakes_first" in user
        assert "try_it" in user
        assert "diagnosis" in user

    def test_practice_prompt_includes_error_tags_and_previous(self):
        system, user = build_concept_practice_question_prompt(
            concept_name="Indefinite integrals",
            subject="Calculus",
            topic="Integrals",
            difficulty="intermediate",
            attempt_number=2,
            known_error_tags=["sign_error", "forgot_constant"],
            previous_questions=[{"question": "Integrate 3x^2", "final_answer": "x^3"}],
            prerequisite_mode=False,
        )
        assert "ExamiQ+" in system
        assert "sign_error" in user
        assert "Integrate 3x^2" in user
        assert "attempt_number" in user.lower() or "Attempt number" in user
        assert "error_tag" in user

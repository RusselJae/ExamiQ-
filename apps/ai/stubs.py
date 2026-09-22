"""Stub AI service implementations (no live API calls)."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.ai.interfaces import (
    AdaptiveFeedbackGenerator,
    CalibrationAnalyzer,
    CurriculumAdvisor,
    DifficultyTagger,
    ErrorClassifier,
    ExplanationGenerator,
    QuestionGenerator,
    SpacedRepetitionScheduler,
    TutorEngine,
)
from apps.reviews.recommendations import get_review_recommendations

logger = logging.getLogger(__name__)

_STUB_LABELS = ("B", "C", "D")


class StubQuestionGenerator(QuestionGenerator):
    def generate(
        self,
        topic,
        difficulty: str,
        count: int = 5,
        reference_stem: str = "",
        source_material: str = "",
        question_type: str = "mcq",
    ):
        from apps.ai.prompts import coerce_generate_question_type

        logger.info("AI question generation stub called (AI_ENABLED=%s)", settings.AI_ENABLED)
        if topic is None:
            return []
        from apps.ai.normalize import normalize_generated_questions

        qtype = coerce_generate_question_type(question_type)
        items = []
        prefix = "[From module] " if source_material else "[Stub] "
        for i in range(min(count, 3)):
            if qtype == "true_false":
                items.append({
                    "question_type": qtype,
                    "stem": f"{prefix}Sample {difficulty} statement about {topic.name}. ({i + 1})",
                    "concept_tag": f"Concept: {topic.name}",
                    "expected_answer": "True" if i % 2 == 0 else "False",
                })
            elif qtype == "identification":
                items.append({
                    "question_type": qtype,
                    "stem": f"{prefix}Name the key term for {topic.name}. ({i + 1})",
                    "concept_tag": f"Concept: {topic.name}",
                    "expected_answer": f"Term {i + 1}",
                })
            elif qtype == "enumeration":
                items.append({
                    "question_type": qtype,
                    "stem": f"{prefix}List sample items for {topic.name}. ({i + 1})",
                    "concept_tag": f"Concept: {topic.name}",
                    "expected_answer": f"Item {i + 1}\nItem {i + 2}",
                })
            else:
                label = _STUB_LABELS[i % len(_STUB_LABELS)]
                items.append({
                    "question_type": "mcq",
                    "stem": f"{prefix}Sample {difficulty} question about {topic.name}? ({i + 1})",
                    "concept_tag": f"Concept: {topic.name}",
                    "correct_label": label,
                    "choices": [
                        {"label": "A", "text": "Distractor A", "is_correct": label == "A"},
                        {"label": "B", "text": "Distractor B", "is_correct": label == "B"},
                        {"label": "C", "text": "Distractor C", "is_correct": label == "C"},
                        {"label": "D", "text": "Distractor D", "is_correct": label == "D"},
                    ],
                })
        return normalize_generated_questions(items, question_type=qtype)


class StubExplanationGenerator(ExplanationGenerator):
    def generate(self, question) -> dict:
        from apps.questions.models import Question

        if question.question_type == Question.QuestionType.MCQ:
            label = ""
            correct = question.choices.filter(is_correct=True).first()
            if correct:
                label = correct.label
            topic_name = question.topic.name if question.topic_id else "this topic"
            return {
                "explanation_steps": [
                    f"Identify the key idea for {topic_name}.",
                    "Eliminate distractors that do not match the concept.",
                    f"Select choice {label or 'the correct option'} as the answer.",
                ],
                "solution_summary": f"The correct answer is {label}." if label else "Review the correct choice.",
            }
        topic_name = question.topic.name if question.topic_id else "this topic"
        answer = (question.expected_answer or "").strip()
        return {
            "explanation_steps": [
                f"Read the {topic_name} question carefully.",
                "Recall the rule or definition that applies.",
                f"The expected answer is: {answer or 'see solution'}.",
            ],
            "solution_summary": answer or "Review the expected answer.",
        }


class StubQuestionValidator:
    def validate(self, stem, choices, topic, difficulty, correct_label=""):
        from apps.ai.interfaces import QuestionValidator

        return QuestionValidator().validate(stem, choices, topic, difficulty, correct_label)


class StubAdaptiveFeedbackGenerator(AdaptiveFeedbackGenerator):
    def generate(
        self,
        topic,
        question,
        user_answer,
        correct_answer,
        confidence="medium",
        question_type="",
        *,
        choices=None,
        difficulty="",
        is_correct=False,
        unanswered=False,
    ):
        from apps.ai.normalize import (
            adaptive_feedback_to_json,
            correct_adaptive_feedback_to_json,
        )

        type_hint = f" ({question_type})" if question_type else ""
        if is_correct:
            return correct_adaptive_feedback_to_json(
                {
                    "why_it_works": (
                        f"'{correct_answer}' is right for {topic}{type_hint} "
                        "because it matches the definition behind the options."
                    ),
                    "remember": "Match the definition to the option.",
                    "worked_example": None,
                    "follow_ups": [
                        f"Why is '{correct_answer}' correct?",
                        "Show a small example",
                        "Quiz me on this",
                    ],
                }
            )

        _ = unanswered
        return adaptive_feedback_to_json(
            {
                "what_went_wrong": (
                    f"You answered '{user_answer}'{type_hint}, which does not "
                    f"match '{correct_answer}'."
                ),
                "why": (
                    f"For {topic}, the correct choice is '{correct_answer}' "
                    "based on the definition and options shown."
                ),
                "quick_check": None,
                "remember": "Match the definition to the option.",
                "follow_ups": [
                    f"Why is '{correct_answer}' correct?",
                    "Show a small example",
                    "Quiz me on this",
                ],
                "solution_steps": None,
            }
        )


class StubDifficultyTagger(DifficultyTagger):
    def tag(self, stem: str, current_difficulty: str) -> str:
        if not stem.strip():
            return current_difficulty
        length = len(stem.split())
        if length > 40:
            return "hard"
        if length > 20:
            return "medium"
        return "easy"


class StubCalibrationAnalyzer(CalibrationAnalyzer):
    pass


class RuleBasedSpacedRepetitionScheduler(SpacedRepetitionScheduler):
    """Rule-based spaced repetition using review recommendations."""

    def next_review_date(self, student, topic):
        recs = get_review_recommendations(student, limit=20)
        for rec in recs:
            if rec["topic"].pk == topic.pk:
                return rec["suggested_date"]
        return timezone.localdate() + timedelta(days=7)


class StubSpacedRepetitionScheduler(SpacedRepetitionScheduler):
    pass


class StubTutorEngine(TutorEngine):
    def chat(
        self,
        topic: str,
        message: str,
        *,
        history: list[dict[str, str]] | None = None,
        exam_context: dict | None = None,
        question_context: dict | None = None,
    ) -> str:
        import json

        stem = (question_context or {}).get("stem", "")
        if stem:
            return json.dumps(
                {
                    "steps": [
                        {
                            "title": f"Focus on {topic}",
                            "operation": "start from the active question",
                            "equations": [],
                            "highlight": "",
                        },
                        {
                            "title": "Check the Solution tab",
                            "operation": "compare your work to the worked steps",
                            "equations": [],
                            "highlight": "",
                        },
                    ],
                    "answer": (question_context or {}).get("correct_answer") or "",
                    "chart": None,
                }
            )
        return json.dumps(
            {
                "steps": [
                    {
                        "title": f"Stay on {topic}",
                        "operation": "pick an exam question to discuss",
                        "equations": [],
                        "highlight": "",
                    }
                ],
                "answer": "",
                "chart": None,
            }
        )


class LiveTutorEngine(TutorEngine):
    def chat(
        self,
        topic: str,
        message: str,
        *,
        history: list[dict[str, str]] | None = None,
        exam_context: dict | None = None,
        question_context: dict | None = None,
    ) -> str:
        from apps.ai.prompts import build_tutor_chat_prompt

        system, user_prompt = build_tutor_chat_prompt(
            topic,
            message,
            history=history,
            exam_context=exam_context,
            question_context=question_context,
        )
        from django.conf import settings

        try:
            if settings.LLM_PROVIDER == "gemini":
                from apps.ai.providers.gemini_client import chat_with_fallback

                return chat_with_fallback(user_prompt, system=system, max_output_tokens=800).text
            if settings.LLM_PROVIDER == "ollama":
                from apps.ai.providers.ollama_client import chat_with_fallback

                return chat_with_fallback(user_prompt, system=system, max_output_tokens=800).text
            from apps.ai.providers.openai_provider import _chat

            result = _chat(user_prompt, system=system)
            if result:
                return result
            raise RuntimeError("OpenAI returned empty response")
        except Exception:
            return StubTutorEngine().chat(
                topic,
                message,
                history=history,
                exam_context=exam_context,
                question_context=question_context,
            )


class StubErrorClassifier(ErrorClassifier):
    pass


class StubCurriculumAdvisor(CurriculumAdvisor):
    pass

"""Stub AI service implementations (no live API calls)."""

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.ai.interfaces import (
    AdaptiveFeedbackGenerator,
    CalibrationAnalyzer,
    ConceptPracticeGenerator,
    ConceptRemediationGenerator,
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


def _stub_normalized_stem(stem: str) -> str:
    """Case-insensitive, whitespace-collapsed stem for exclusion matching."""
    import re

    return re.sub(r"\s+", " ", (stem or "").strip().lower())


def _stub_explanation_fields(topic_name: str, answer_hint: str) -> dict:
    """Shared explanation + adaptive fields for stub-generated questions."""
    return {
        "explanation_steps": [
            f"Identify the key idea for {topic_name}.",
            "Apply the rule that matches the stem.",
            f"Arrive at: {answer_hint}.",
        ],
        "solution_summary": f"Answer: {answer_hint}.",
        "what_went_wrong": (
            "A common miss is choosing a familiar distractor that skips a key condition."
        ),
        "why": f"The correct answer follows the core idea for {topic_name}.",
        "quick_check": f"Quick check: does the result match {answer_hint}?",
        "remember": "Check the defining condition first.",
        "worked_example": "",
    }


class StubQuestionGenerator(QuestionGenerator):
    def generate(
        self,
        topic,
        difficulty: str,
        count: int = 5,
        reference_stem: str = "",
        source_material: str = "",
        question_type: str = "mcq",
        exclude_stems: list[str] | None = None,
    ):
        from apps.ai.prompts import coerce_generate_question_type

        logger.info("AI question generation stub called (AI_ENABLED=%s)", settings.AI_ENABLED)
        if topic is None:
            return []
        from apps.ai.normalize import normalize_generated_questions

        qtype = coerce_generate_question_type(question_type)
        items = []
        prefix = "[From module] " if source_material else "[Stub] "
        topic_name = topic.name
        for i in range(min(count, 3)):
            if qtype == "true_false":
                answer = "True" if i % 2 == 0 else "False"
                items.append({
                    "question_type": qtype,
                    "stem": f"{prefix}Sample {difficulty} statement about {topic_name}. ({i + 1})",
                    "concept_tag": f"Concept: {topic_name}",
                    "expected_answer": answer,
                    **_stub_explanation_fields(topic_name, answer),
                })
            elif qtype == "identification":
                answer = f"Term {i + 1}"
                items.append({
                    "question_type": qtype,
                    "stem": f"{prefix}Name the key term for {topic_name}. ({i + 1})",
                    "concept_tag": f"Concept: {topic_name}",
                    "expected_answer": answer,
                    **_stub_explanation_fields(topic_name, answer),
                })
            elif qtype == "enumeration":
                answer = f"Item {i + 1}\nItem {i + 2}"
                items.append({
                    "question_type": qtype,
                    "stem": f"{prefix}List sample items for {topic_name}. ({i + 1})",
                    "concept_tag": f"Concept: {topic_name}",
                    "expected_answer": answer,
                    **_stub_explanation_fields(topic_name, "the listed items"),
                })
            else:
                label = _STUB_LABELS[i % len(_STUB_LABELS)]
                items.append({
                    "question_type": "mcq",
                    "stem": f"{prefix}Sample {difficulty} question about {topic_name}? ({i + 1})",
                    "concept_tag": f"Concept: {topic_name}",
                    "correct_label": label,
                    "choices": [
                        {"label": "A", "text": "Distractor A", "is_correct": label == "A"},
                        {"label": "B", "text": "Distractor B", "is_correct": label == "B"},
                        {"label": "C", "text": "Distractor C", "is_correct": label == "C"},
                        {"label": "D", "text": "Distractor D", "is_correct": label == "D"},
                    ],
                    **_stub_explanation_fields(topic_name, f"choice {label}"),
                })
        items = [
            item
            for item in items
            if _stub_normalized_stem(item.get("stem", ""))
            not in {
                _stub_normalized_stem(stem) for stem in (exclude_stems or [])
            }
        ]
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
                "what_went_wrong": (
                    "A common miss is choosing a distractor that looks familiar "
                    "but skips a defining condition."
                ),
                "why": (
                    f"The correct choice follows the core idea for {topic_name}."
                ),
                "quick_check": None,
                "remember": "Check the defining condition first.",
                "worked_example": None,
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
            "what_went_wrong": (
                "Students often stop at a partial recall instead of the full rule."
            ),
            "why": f"The expected answer matches the rule for {topic_name}.",
            "quick_check": None,
            "remember": "State the full rule before answering.",
            "worked_example": None,
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
        shared_base=None,
    ):
        from apps.ai.normalize import (
            adaptive_feedback_to_json,
            correct_adaptive_feedback_to_json,
            parse_adaptive_feedback,
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
        if shared_base and isinstance(shared_base, dict):
            parsed = parse_adaptive_feedback(shared_base)
            if parsed:
                user = (user_answer or "").strip()
                wrong = parsed.get("what_went_wrong") or ""
                if user and user.lower() not in wrong.lower():
                    parsed["what_went_wrong"] = (
                        f"You chose {user}. {wrong}".strip()
                        if wrong
                        else f"You chose {user}, which is not correct."
                    )
                return adaptive_feedback_to_json(parsed)

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


def _stub_follow_ups() -> list[str]:
    return ["Why is this the answer?", "Show another example", "What should I avoid?"]


def _stub_text_reply(topic: str) -> str:
    return json.dumps(
        {
            "type": "text",
            "blocks": [
                {
                    "kind": "paragraph",
                    "text": f"Quick tutoring notes for {topic or 'this lesson'}.",
                },
                {
                    "kind": "list",
                    "items": [
                        "Pick an exam question to discuss.",
                        "Ask for the rule behind any step.",
                    ],
                },
                {
                    "kind": "table",
                    "headers": ["Action", "Why it helps"],
                    "rows": [
                        ["Name the rule", "Justifies each step"],
                        ["Check the last line", "Catches sign and copy errors"],
                    ],
                },
            ],
            "remember": "Name the rule before applying it.",
            "follow_ups": [
                "Which question confused me?",
                "Explain the main rule",
                "Show an example",
            ],
        }
    )


def _stub_solution_reply(topic: str, ctx: dict) -> str:
    return json.dumps(
        {
            "type": "solution",
            "steps": [
                {
                    "title": f"Recall the {topic or 'topic'} rule",
                    "latex": ["\\text{rule} : \\text{name it first}"],
                    "explain": "Naming the rule first justifies every later line.",
                },
                {
                    "title": "Apply the rule",
                    "latex": ["\\text{apply} : \\text{term} = 2\\hl{x - 1}"],
                    "explain": "The highlighted term is what changed after applying the rule.",
                },
            ],
            "answer": (ctx.get("correct_answer") or "").strip()
            or "\\text{value from the rule}",
            "check": "Compare the final line back to the active question.",
            "follow_ups": _stub_follow_ups(),
        }
    )


def _stub_concept_check_reply(ctx: dict) -> str:
    choices = [
        choice
        for choice in (ctx.get("choices") or [])
        if str((choice or {}).get("id") or "").strip()
    ]
    correct = (ctx.get("correct_pick") or "").strip() or next(
        (str(choice["id"]) for choice in choices), "A"
    )
    if choices:
        options = [
            {
                "id": choice["id"],
                "text": str(choice.get("text") or "").strip(),
                "fits": choice["id"] == correct,
                "reason": (
                    "matches the defining condition in the stem"
                    if choice["id"] == correct
                    else "skips a condition required by the stem"
                ),
            }
            for choice in choices
        ]
    else:
        options = [
            {"id": "A", "fits": False, "reason": "skips a condition required by the stem"},
            {"id": "B", "fits": False, "reason": "confuses a different rule"},
            {"id": "C", "fits": True, "reason": "matches the defining condition"},
        ]
    student_pick = (ctx.get("student_pick") or "").strip() or None
    mistake = None
    if student_pick and student_pick != correct:
        mistake = (
            f"Option {student_pick} reads one clause but skips the defining condition."
        )
    return json.dumps(
        {
            "type": "concept_check",
            "student_pick": student_pick,
            "correct": correct,
            "mistake": mistake,
            "rule": "Test each option against the defining condition in the stem.",
            "options": options,
            "symbolic": None,
            "quick_check": "Does 'and' make a statement simple or compound?",
            "remember": "Test the defining condition first.",
            "follow_ups": [
                f"Why is option {correct} correct?",
                f"Why not option {student_pick}?" if student_pick else "Test one option now",
                "State the rule again",
            ],
        }
    )


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
        ctx = question_context or {}
        if not (ctx or {}).get("stem", ""):
            return _stub_text_reply(topic)
        lowered = (message or "").strip().lower()
        concept_triggers = (
            "which",
            "option",
            "true or false",
            "correct",
            "classify",
        )
        if any(trigger in lowered for trigger in concept_triggers) or (
            "student_pick" in ctx
        ):
            return _stub_concept_check_reply(ctx)
        return _stub_solution_reply(topic, ctx)


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

                return chat_with_fallback(
                    user_prompt,
                    system=system,
                    max_output_tokens=1200,
                    json_mode=True,
                ).text
            if settings.LLM_PROVIDER == "ollama":
                from apps.ai.providers.ollama_client import chat_with_fallback

                return chat_with_fallback(
                    user_prompt,
                    system=system,
                    max_output_tokens=1200,
                    json_mode=True,
                ).text
            from apps.ai.providers.openai_provider import _chat

            result = _chat(
                user_prompt,
                system=system,
                max_output_tokens=1200,
                json_mode=True,
            )
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


class StubConceptRemediationGenerator(ConceptRemediationGenerator):
    def generate(
        self,
        *,
        concept_name: str,
        subject: str,
        topic: str,
        difficulty: str = "beginner",
        miss_count: int = 1,
        missed_questions: list | None = None,
        previous_feedback_styles: list | None = None,
        student_stage: str = "first_review",
        prerequisites: list | None = None,
        preferred_style: str = "worked_example",
    ) -> dict:
        style = preferred_style or "worked_example"
        if style not in {
            "worked_example",
            "analogy",
            "mistakes_first",
            "backwards",
        }:
            style = "worked_example"
        _ = (
            subject,
            topic,
            difficulty,
            miss_count,
            missed_questions,
            previous_feedback_styles,
            student_stage,
            prerequisites,
        )
        return {
            "diagnosis": {
                "type": "knowledge_gap",
                "what_went_wrong": (
                    f"You missed items on {concept_name}. That usually means "
                    "a key first step or rule is incomplete."
                ),
                "prerequisite_flag": None,
            },
            "explanation": {
                "style_used": style,
                "core_idea": (
                    f"For {concept_name}, undo operations in a clear order and "
                    "check each transform before moving on."
                ),
                "key_rules": [
                    "Name the goal of the first step.",
                    "Apply one operation at a time.",
                    "Check by substituting back.",
                ],
            },
            "worked_example": {
                "problem": f"Work a small example for {concept_name}: solve $3x + 5 = 20$.",
                "steps": [
                    {
                        "step": "Subtract $5$ from both sides: $3x = 15$",
                        "why": "Undo addition first.",
                    },
                    {
                        "step": "Divide both sides by $3$: $x = 5$",
                        "why": "Undo multiplication next.",
                    },
                    {
                        "step": "Check: $3(5) + 5 = 20$",
                        "why": "Substitution confirms the solution.",
                    },
                ],
                "final_answer": "$x = 5$",
            },
            "common_mistakes": [
                {
                    "mistake": "Doing the multiply/divide step before undoing add/subtract.",
                    "why_it_fails": "It leaves an extra term attached to $x$.",
                    "fix": "Undo +/− first, then ×/÷.",
                },
                {
                    "mistake": "Adding when you should subtract.",
                    "why_it_fails": "The constant moves farther from isolation.",
                    "fix": "Use the opposite of the shown operation.",
                },
            ],
            "try_it": {
                "problem": "Solve $4x + 9 = 33$. Which step should come first?",
                "first_step_choices": [
                    "Divide both sides by $4$",
                    "Add $9$ to both sides",
                    "Subtract $9$ from both sides",
                ],
                "correct_index": 2,
                "hint": "Undo the constant term before touching the coefficient of $x$.",
                "feedback_if_wrong": (
                    "Not quite. To undo $+9$, subtract $9$ from both sides first."
                ),
            },
            "check_yourself": (
                "Substitute your answer into the original equation and confirm both sides match."
            ),
        }


class StubConceptPracticeGenerator(ConceptPracticeGenerator):
    def generate(
        self,
        *,
        concept_name: str,
        subject: str,
        topic: str,
        difficulty: str = "beginner",
        attempt_number: int = 1,
        known_error_tags: list | None = None,
        previous_questions: list | None = None,
        prerequisite_mode: bool = False,
        prerequisite_concept: str = "",
    ) -> dict:
        _ = (subject, topic, previous_questions, prerequisite_mode, prerequisite_concept)
        # Vary numbers slightly by attempt so repeats are not identical.
        addend = 3 + (attempt_number % 5)
        coeff = 2 + (attempt_number % 3)
        right = coeff * 6 + addend
        correct = str(6)
        tags = list(known_error_tags or [])
        primary_tag = tags[0] if tags else "wrong_operation_order"
        return {
            "concept": concept_name,
            "difficulty": difficulty if difficulty in {
                "beginner", "intermediate", "advanced"
            } else "beginner",
            "question": (
                f"Solve ${coeff}x + {addend} = {right}$. What is $x$?"
            ),
            "options": [
                {
                    "id": "A",
                    "text": str(right - addend),
                    "is_correct": False,
                    "error_tag": "forgot_to_divide",
                    "why_wrong": (
                        f"You subtracted {addend} but did not divide by {coeff}."
                    ),
                },
                {
                    "id": "B",
                    "text": correct,
                    "is_correct": True,
                    "error_tag": None,
                    "why_wrong": None,
                },
                {
                    "id": "C",
                    "text": str(right + addend),
                    "is_correct": False,
                    "error_tag": "sign_error",
                    "why_wrong": (
                        f"Adding {addend} instead of subtracting moves the constant the wrong way."
                    ),
                },
                {
                    "id": "D",
                    "text": str((right + addend) // coeff if coeff else 0),
                    "is_correct": False,
                    "error_tag": primary_tag,
                    "why_wrong": (
                        "This mixes the wrong first operation with dividing by the coefficient."
                    ),
                },
            ],
            "hint": f"First undo the $+{addend}$ term on the left side.",
            "solution_steps": [
                f"Subtract ${addend}$ from both sides: ${coeff}x = {right - addend}$.",
                f"Divide both sides by ${coeff}$: $x = {correct}$.",
                f"Check: ${coeff}({correct}) + {addend} = {right}$.",
            ],
            "final_answer": f"$x = {correct}$",
            "self_check": (
                f"Plug $x = {correct}$ back into ${coeff}x + {addend}$ and confirm it equals ${right}$."
            ),
        }

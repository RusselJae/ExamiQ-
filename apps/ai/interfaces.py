"""AI service interfaces for LLM integration."""

from typing import Any


class QuestionValidator:
    def validate(
        self,
        stem: str,
        choices: list[dict],
        topic,
        difficulty: str,
        correct_label: str = "",
    ) -> dict:
        return {
            "is_valid": True,
            "topic_relevant": True,
            "answer_correct": True,
            "feedback": "AI validation is disabled. Review manually before submitting.",
            "suggested_concept_tag": "",
        }


class QuestionGenerator:
    def generate(
        self,
        topic,
        difficulty: str,
        count: int = 5,
        reference_stem: str = "",
        source_material: str = "",
        question_type: str = "mcq",
    ) -> list[dict]:
        return []


class ExplanationGenerator:
    def generate(self, question) -> dict:
        """Return ``{"explanation_steps": [...], "solution_summary": "..."}``."""
        return {"explanation_steps": [], "solution_summary": ""}


class DifficultyTagger:
    def tag(self, stem: str, current_difficulty: str) -> str:
        return current_difficulty


class CalibrationAnalyzer:
    def analyze(self, student, answers_qs, weak_topics: list | None = None) -> dict[str, Any]:
        from apps.analytics.confidence import confidence_accuracy_matrix
        from apps.ai.helpers import calibration_narrative_from_matrix

        matrix = confidence_accuracy_matrix(answers_qs)
        return {
            "matrix": matrix,
            "narrative": calibration_narrative_from_matrix(matrix, weak_topics),
            "ai_enabled": False,
        }


class SpacedRepetitionScheduler:
    def next_review_date(self, student, topic):
        return None


class TutorEngine:
    def reexplain(self, step, student_history: dict | None = None) -> str:
        return step.content

    def chat(
        self,
        topic: str,
        message: str,
        *,
        history: list[dict[str, str]] | None = None,
        exam_context: dict | None = None,
        question_context: dict | None = None,
    ) -> str:
        return (
            f"Let's focus on {topic}. Ask about the exam question or the steps to solve it."
        )


class ErrorClassifier:
    def classify(self, question, answer):
        return None


class AdaptiveFeedbackGenerator:
    def generate(
        self,
        topic: str,
        question: str,
        user_answer: str,
        correct_answer: str,
        confidence: str = "medium",
        question_type: str = "",
        *,
        choices: list[str] | None = None,
        difficulty: str = "",
        is_correct: bool = False,
        unanswered: bool = False,
    ) -> str:
        """Return validated adaptive feedback JSON (or plain fallback text)."""
        from apps.ai.normalize import (
            adaptive_feedback_to_json,
            correct_adaptive_feedback_to_json,
        )

        if is_correct:
            payload = {
                "why_it_works": (
                    f"'{correct_answer}' holds for {topic} because it matches "
                    "the definition and the options given."
                ),
                "remember": "Match the definition to the option.",
                "worked_example": None,
                "follow_ups": [
                    f"Why is '{correct_answer}' right?",
                    "Give a tiny example",
                    "Quiz me on this",
                ],
            }
            return correct_adaptive_feedback_to_json(payload)

        _ = unanswered
        payload = {
            "what_went_wrong": (
                f"You chose '{user_answer}', which conflicts with the correct "
                f"result '{correct_answer}'."
            ),
            "why": (
                f"The correct answer holds for {topic} because it matches the "
                "definition and the options given."
            ),
            "quick_check": None,
            "remember": "Match the definition to the option.",
            "follow_ups": [
                f"Why is '{correct_answer}' right?",
                "Give a tiny example",
                "Quiz me on this",
            ],
            "solution_steps": None,
        }
        return adaptive_feedback_to_json(payload)


class CurriculumAdvisor:
    def program_report(self, program) -> str:
        from apps.analytics.services import program_performance_summary

        summary = program_performance_summary(program)
        return (
            f"{program.name}: {summary['accuracy']}% accuracy across "
            f"{summary['sessions_completed']} sessions. "
            "Enable AI for automated curriculum recommendations."
        )

    def course_report(self, course) -> str:
        from apps.analytics.services import course_performance_summary
        from apps.ai.helpers import course_review_narrative

        summary = course_performance_summary(course)
        return course_review_narrative(summary)

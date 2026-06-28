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
    def generate(self, topic, difficulty: str, count: int = 5, reference_stem: str = "") -> list[dict]:
        return []


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
    ) -> str:
        return (
            f"You answered '{user_answer}' but the correct answer is '{correct_answer}'. "
            f"Review {topic} and practice similar problems."
        )


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

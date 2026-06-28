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
    QuestionGenerator,
    SpacedRepetitionScheduler,
    TutorEngine,
)
from apps.reviews.recommendations import get_review_recommendations

logger = logging.getLogger(__name__)

_STUB_LABELS = ("B", "C", "D")


class StubQuestionGenerator(QuestionGenerator):
    def generate(self, topic, difficulty: str, count: int = 5, reference_stem: str = ""):
        logger.info("AI question generation stub called (AI_ENABLED=%s)", settings.AI_ENABLED)
        if topic is None:
            return []
        from apps.ai.normalize import normalize_generated_questions

        items = []
        for i in range(min(count, 3)):
            label = _STUB_LABELS[i % len(_STUB_LABELS)]
            items.append({
                "stem": f"[Stub] Sample {difficulty} question about {topic.name}? ({i + 1})",
                "concept_tag": f"Concept: {topic.name}",
                "correct_label": label,
                "choices": [
                    {"label": "A", "text": "Distractor A", "is_correct": label == "A"},
                    {"label": "B", "text": "Distractor B", "is_correct": label == "B"},
                    {"label": "C", "text": "Distractor C", "is_correct": label == "C"},
                    {"label": "D", "text": "Distractor D", "is_correct": label == "D"},
                ],
                "explanation_steps": [
                    f"Step 1: Identify the concept related to {topic.name}.",
                    f"Step 2: Apply the rule; the correct choice is {label}.",
                ],
                "solution_summary": f"The correct answer is {label}.",
            })
        return normalize_generated_questions(items)


class StubQuestionValidator:
    def validate(self, stem, choices, topic, difficulty, correct_label=""):
        from apps.ai.interfaces import QuestionValidator

        return QuestionValidator().validate(stem, choices, topic, difficulty, correct_label)


class StubAdaptiveFeedbackGenerator(AdaptiveFeedbackGenerator):
    def generate(self, topic, question, user_answer, correct_answer, confidence="medium"):
        return (
            f"You answered '{user_answer}' but the correct answer is '{correct_answer}'. "
            f"Review the core concept for {topic} and try similar practice questions."
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
    pass


class StubErrorClassifier(ErrorClassifier):
    pass


class StubCurriculumAdvisor(CurriculumAdvisor):
    pass

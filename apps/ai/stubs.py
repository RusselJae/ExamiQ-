"""Stub AI service implementations (no live API calls)."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.ai.interfaces import (
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


class StubQuestionGenerator(QuestionGenerator):
    def generate(self, topic, difficulty: str, count: int = 5, reference_stem: str = ""):
        logger.info("AI question generation stub called (AI_ENABLED=%s)", settings.AI_ENABLED)
        if topic is None:
            return []
        return [
            {
                "stem": f"[Stub] Sample {difficulty} question about {topic.name}?",
                "concept_tag": f"Concept: {topic.name}",
                "correct_label": "A",
                "choices": [
                    {"label": "A", "text": "Correct answer", "is_correct": True},
                    {"label": "B", "text": "Distractor 1", "is_correct": False},
                    {"label": "C", "text": "Distractor 2", "is_correct": False},
                    {"label": "D", "text": "Distractor 3", "is_correct": False},
                ],
            }
            for _ in range(min(count, 3))
        ]


class StubQuestionValidator:
    def validate(self, stem, choices, topic, difficulty, correct_label=""):
        from apps.ai.interfaces import QuestionValidator

        return QuestionValidator().validate(stem, choices, topic, difficulty, correct_label)


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

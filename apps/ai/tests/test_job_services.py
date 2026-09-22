from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.job_services import (
    _chunk_sizes,
    run_explanation_generation_job,
    run_question_generation_job,
    start_question_generation_job,
)
from apps.ai.models import AIGenerationJob
from apps.ai.normalize import normalize_generated_questions
from apps.questions.models import ExplanationStep


def _make_question_batch(count: int, stem_prefix: str = "Q") -> list[dict]:
    return [
        {
            "stem": f"{stem_prefix}-{i}",
            "choices": [
                {"label": "A", "text": f"{i}-a", "is_correct": True},
                {"label": "B", "text": f"{i}-b", "is_correct": False},
                {"label": "C", "text": f"{i}-c", "is_correct": False},
                {"label": "D", "text": f"{i}-d", "is_correct": False},
            ],
            "correct_label": "A",
            "concept_tag": "Concept",
        }
        for i in range(count)
    ]


def _create_job(*, professor, course, topic, count: int, difficulty: str = "easy", question_type: str = "mcq") -> AIGenerationJob:
    return AIGenerationJob.objects.create(
        job_type=AIGenerationJob.JobType.QUESTION_GENERATE,
        status=AIGenerationJob.Status.PENDING,
        created_by=professor,
        course_id=course.pk,
        topic_id=topic.pk,
        difficulty=difficulty,
        count=count,
        question_type=question_type,
        source_material="Module text about linear equations.",
    )


def _run(generator, job_id: int) -> AIGenerationJob:
    """Run the job synchronously with a mocked generator and patched backoff sleep."""
    with (
        patch("apps.ai.job_services.get_question_generator", return_value=generator),
        patch("apps.ai.job_services.time.sleep"),
    ):
        run_question_generation_job(job_id)
    return AIGenerationJob.objects.get(pk=job_id)


class TestChunkSizes:
    def test_chunk_sizes(self):
        assert _chunk_sizes(0, 5) == []
        assert _chunk_sizes(3, 5) == [3]
        assert _chunk_sizes(10, 5) == [5, 5]
        assert _chunk_sizes(7, 5) == [5, 2]
        assert _chunk_sizes(10, 0) == []


@pytest.mark.django_db
class TestQuestionGenerationJob:
    @override_settings(AI_GENERATION_MAX_COUNT=50)
    def test_start_job_clamps_large_count(self, professor, course, topic):
        """Generation count is capped by AI_GENERATION_MAX_COUNT."""
        with patch("apps.ai.job_services.threading.Thread") as thread_cls:
            thread_cls.return_value = MagicMock()
            job = start_question_generation_job(
                user=professor,
                course_id=course.pk,
                topic_id=topic.pk,
                difficulty="easy",
                count=99,
                source_material="Module text",
            )
        assert job.count == 50

    @override_settings(AI_GENERATION_BATCH_SIZE=5, AI_GENERATION_MAX_ATTEMPTS=3)
    def test_batches_generation_calls(self, professor, course, topic):
        generator = MagicMock()
        generator.generate.side_effect = [
            normalize_generated_questions(_make_question_batch(5, "A")),
            normalize_generated_questions(_make_question_batch(5, "B")),
        ]
        job = _create_job(professor=professor, course=course, topic=topic, count=10)
        job = _run(generator, job.pk)

        assert job.status == AIGenerationJob.Status.SUCCEEDED
        assert generator.generate.call_count == 2
        counts = [call.kwargs["count"] for call in generator.generate.call_args_list]
        assert counts == [5, 5]
        assert len(job.result["variations"]) == 10

    @override_settings(AI_GENERATION_BATCH_SIZE=5, AI_GENERATION_MAX_ATTEMPTS=3)
    def test_retries_retryable_failure_then_succeeds(self, professor, course, topic):
        generator = MagicMock()
        generator.generate.side_effect = [
            AIServiceUnavailableError("AI unavailable: API quota exceeded.", retryable=True),
            normalize_generated_questions(_make_question_batch(3, "Q")),
        ]
        job = _create_job(professor=professor, course=course, topic=topic, count=3)
        job = _run(generator, job.pk)

        assert job.status == AIGenerationJob.Status.SUCCEEDED
        assert generator.generate.call_count == 2
        assert len(job.result["variations"]) == 3

    @override_settings(AI_GENERATION_BATCH_SIZE=5, AI_GENERATION_MAX_ATTEMPTS=3)
    def test_retryable_failure_exhausts_and_fails(self, professor, course, topic):
        generator = MagicMock()
        generator.generate.side_effect = AIServiceUnavailableError(
            "AI unavailable: API quota exceeded.", retryable=True
        )
        job = _create_job(professor=professor, course=course, topic=topic, count=3)
        job = _run(generator, job.pk)

        assert job.status == AIGenerationJob.Status.FAILED
        assert generator.generate.call_count == 3
        assert "quota" in job.error_message

    @override_settings(AI_GENERATION_BATCH_SIZE=5, AI_GENERATION_MAX_ATTEMPTS=3)
    def test_non_retryable_failure_fails_immediately(self, professor, course, topic):
        generator = MagicMock()
        generator.generate.side_effect = AIServiceUnavailableError(
            "AI unavailable: invalid or missing Ollama API key.", retryable=False
        )
        job = _create_job(professor=professor, course=course, topic=topic, count=3)
        job = _run(generator, job.pk)

        assert job.status == AIGenerationJob.Status.FAILED
        assert generator.generate.call_count == 1
        assert "API key" in job.error_message


def _create_explanation_job(*, professor, course, topic, question_ids: list[int]) -> AIGenerationJob:
    return AIGenerationJob.objects.create(
        job_type=AIGenerationJob.JobType.EXPLANATION_GENERATE,
        status=AIGenerationJob.Status.PENDING,
        created_by=professor,
        course_id=course.pk,
        topic_id=topic.pk,
        count=len(question_ids),
        result={"question_ids": question_ids, "completed_ids": [], "failed_ids": []},
    )


def _run_explanation(generator, job_id: int) -> AIGenerationJob:
    with (
        patch("apps.ai.job_services.get_explanation_generator", return_value=generator),
        patch("apps.ai.job_services.time.sleep"),
    ):
        run_explanation_generation_job(job_id)
    return AIGenerationJob.objects.get(pk=job_id)


@pytest.mark.django_db
class TestExplanationGenerationJob:
    def test_writes_steps_for_questions_without_explanations(
        self, professor, course, topic, mcq_question
    ):
        question, _correct = mcq_question
        generator = MagicMock()
        generator.generate.return_value = {
            "explanation_steps": ["Add both numbers.", "2 + 2 = 4"],
            "solution_summary": "The correct answer is A.",
            "what_went_wrong": "Students often add across instead of combining like terms.",
            "why": "Only like terms can be combined.",
            "quick_check": "2x + 3x = 5x.",
            "remember": "Combine like terms only.",
            "worked_example": None,
        }
        job = _create_explanation_job(
            professor=professor,
            course=course,
            topic=topic,
            question_ids=[question.pk],
        )
        job = _run_explanation(generator, job.pk)

        assert job.status == AIGenerationJob.Status.SUCCEEDED
        steps = list(
            ExplanationStep.objects.filter(question=question).order_by("order").values_list(
                "content", flat=True
            )
        )
        assert steps == ["Add both numbers.", "2 + 2 = 4"]
        question.refresh_from_db()
        assert question.adaptive_explanation["remember"] == "Combine like terms only."
        assert question.adaptive_explanation_source == "ai"
        assert generator.generate.call_count == 1

    def test_skips_when_steps_and_adaptive_already_exist(
        self, professor, course, topic, mcq_question
    ):
        question, _correct = mcq_question
        ExplanationStep.objects.create(question=question, order=1, content="Existing step.")
        question.adaptive_explanation = {
            "what_went_wrong": "Existing.",
            "why": "Existing why.",
            "quick_check": "",
            "remember": "Existing hook.",
            "worked_example": "",
        }
        question.adaptive_explanation_source = "faculty"
        question.save(
            update_fields=["adaptive_explanation", "adaptive_explanation_source"]
        )
        generator = MagicMock()
        job = _create_explanation_job(
            professor=professor,
            course=course,
            topic=topic,
            question_ids=[question.pk],
        )
        job = _run_explanation(generator, job.pk)

        assert job.status == AIGenerationJob.Status.SUCCEEDED
        generator.generate.assert_not_called()
        assert ExplanationStep.objects.filter(question=question).count() == 1
        question.refresh_from_db()
        assert question.adaptive_explanation_source == "faculty"

    def test_retries_then_succeeds(self, professor, course, topic, mcq_question):
        question, _correct = mcq_question
        generator = MagicMock()
        generator.generate.side_effect = [
            AIServiceUnavailableError("AI unavailable: API quota exceeded.", retryable=True),
            {
                "explanation_steps": ["Work the problem."],
                "solution_summary": "Answer A.",
            },
        ]
        job = _create_explanation_job(
            professor=professor,
            course=course,
            topic=topic,
            question_ids=[question.pk],
        )
        job = _run_explanation(generator, job.pk)

        assert job.status == AIGenerationJob.Status.SUCCEEDED
        assert generator.generate.call_count == 2
        assert ExplanationStep.objects.filter(question=question).exists()

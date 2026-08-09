from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.job_services import _chunk_sizes, run_question_generation_job
from apps.ai.models import AIGenerationJob
from apps.ai.normalize import normalize_generated_questions


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
            "explanation_steps": ["Step 1", "Step 2"],
            "solution_summary": f"Answer {i}-a",
        }
        for i in range(count)
    ]


def _create_job(*, professor, course, topic, count: int, difficulty: str = "easy") -> AIGenerationJob:
    return AIGenerationJob.objects.create(
        job_type=AIGenerationJob.JobType.QUESTION_GENERATE,
        status=AIGenerationJob.Status.PENDING,
        created_by=professor,
        course_id=course.pk,
        topic_id=topic.pk,
        difficulty=difficulty,
        count=count,
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

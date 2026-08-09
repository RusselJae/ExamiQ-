"""Background helpers for AIGenerationJob (thread-based, no Celery required)."""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.factory import get_question_generator
from apps.ai.models import AIGenerationJob
from apps.ai.normalize import normalize_generated_questions
from apps.questions.models import Topic

logger = logging.getLogger(__name__)


def _chunk_sizes(total: int, size: int) -> list[int]:
    """Split ``total`` into a list of chunk sizes of at most ``size`` each."""
    if total <= 0 or size <= 0:
        return []
    return [min(size, total - start) for start in range(0, total, size)]


def start_question_generation_job(
    *,
    user,
    course_id: int,
    topic_id: int,
    difficulty: str,
    count: int = 3,
    source_material: str = "",
    learning_document=None,
) -> AIGenerationJob:
    job = AIGenerationJob.objects.create(
        job_type=AIGenerationJob.JobType.QUESTION_GENERATE,
        status=AIGenerationJob.Status.PENDING,
        created_by=user,
        course_id=course_id,
        topic_id=topic_id,
        difficulty=difficulty,
        count=max(1, min(count, 10)),
        source_material=source_material or "",
        learning_document=learning_document,
    )
    thread = threading.Thread(
        target=run_question_generation_job,
        args=(job.pk,),
        daemon=True,
        name=f"ai-question-job-{job.pk}",
    )
    thread.start()
    return job


def run_question_generation_job(job_id: int) -> None:
    close_old_connections()
    try:
        job = AIGenerationJob.objects.get(pk=job_id)
    except AIGenerationJob.DoesNotExist:
        return

    job.status = AIGenerationJob.Status.RUNNING
    job.save(update_fields=["status", "updated"])

    variations: list[dict] = []

    try:
        topic = Topic.objects.select_related("subject", "subject__program").get(pk=job.topic_id)
        source_material = job.source_material or ""
        if job.learning_document_id and not source_material:
            from apps.ai.retrieval import retrieve_material_for_topic

            source_material = retrieve_material_for_topic(
                document=job.learning_document,
                topic=topic,
            )
            if source_material:
                job.source_material = source_material
                job.save(update_fields=["source_material", "updated"])

        generator = get_question_generator()
        # Generate in small batches instead of one call per question: this cuts
        # provider request usage (e.g. ~20 requests -> 2 for 10 questions) and
        # keeps each call within the output-token budget. Retry transient
        # provider failures (rate limits, 5xx) with exponential backoff.
        batch_size = getattr(settings, "AI_GENERATION_BATCH_SIZE", 5)
        max_attempts = getattr(settings, "AI_GENERATION_MAX_ATTEMPTS", 3)
        for chunk in _chunk_sizes(job.count, batch_size):
            attempt = 0
            last_exc: AIServiceUnavailableError | None = None
            while attempt < max_attempts:
                try:
                    batch = normalize_generated_questions(
                        generator.generate(
                            topic,
                            job.difficulty,
                            count=chunk,
                            source_material=source_material,
                        )
                    )
                    variations.extend(batch)
                    break
                except AIServiceUnavailableError as exc:
                    last_exc = exc
                    if not exc.retryable:
                        raise
                    attempt += 1
                    if attempt < max_attempts:
                        time.sleep(min(2**attempt, 8))
            else:
                if last_exc is not None:
                    raise last_exc
            if len(variations) >= job.count:
                break

        job.result = {"variations": variations[: job.count]}
        job.status = AIGenerationJob.Status.SUCCEEDED
        job.error_message = ""
        job.save(update_fields=["result", "status", "error_message", "updated"])
    except AIServiceUnavailableError as exc:
        logger.warning("AI question job %s failed: %s", job_id, exc.message)
        job.status = AIGenerationJob.Status.FAILED
        job.error_message = exc.message
        job.result = {"variations": variations[: job.count]}
        job.save(update_fields=["status", "error_message", "result", "updated"])
    except Exception as exc:
        logger.exception("AI question job %s crashed", job_id)
        job.status = AIGenerationJob.Status.FAILED
        job.error_message = "Question generation failed. Please try again."
        job.result = {"variations": variations[: job.count]}
        job.save(update_fields=["status", "error_message", "result", "updated"])
    finally:
        close_old_connections()

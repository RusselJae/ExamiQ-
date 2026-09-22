"""Background helpers for AIGenerationJob (thread-based, no Celery required)."""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.factory import get_explanation_generator, get_question_generator, is_ai_configured
from apps.ai.models import AIGenerationJob
from apps.ai.normalize import normalize_generated_questions
from apps.ai.prompts import coerce_generate_question_type
from apps.questions.models import ExplanationStep, Question, Topic

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
    question_type: str = "mcq",
    reference_stem: str = "",
    reference_question_id: int | None = None,
) -> AIGenerationJob:
    qtype = coerce_generate_question_type(question_type)
    max_count = int(getattr(settings, "AI_GENERATION_MAX_COUNT", 50) or 50)
    clamped = max(1, int(count))
    if max_count > 0:
        clamped = min(clamped, max_count)
    job = AIGenerationJob.objects.create(
        job_type=AIGenerationJob.JobType.QUESTION_GENERATE,
        status=AIGenerationJob.Status.PENDING,
        created_by=user,
        course_id=course_id,
        topic_id=topic_id,
        difficulty=difficulty,
        count=clamped,
        question_type=qtype,
        source_material=source_material or "",
        learning_document=learning_document,
        reference_stem=(reference_stem or "").strip(),
        reference_question_id=reference_question_id,
    )
    thread = threading.Thread(
        target=run_question_generation_job,
        args=(job.pk,),
        daemon=True,
        name=f"ai-question-job-{job.pk}",
    )
    thread.start()
    return job


def start_explanation_generation_job(
    *,
    user,
    course_id: int,
    topic_id: int,
    question_ids: list[int],
) -> AIGenerationJob | None:
    """Enqueue background explanation generation for saved questions."""
    ids = [int(pk) for pk in question_ids if pk]
    if not ids or not is_ai_configured():
        return None

    job = AIGenerationJob.objects.create(
        job_type=AIGenerationJob.JobType.EXPLANATION_GENERATE,
        status=AIGenerationJob.Status.PENDING,
        created_by=user,
        course_id=course_id,
        topic_id=topic_id,
        difficulty="",
        count=len(ids),
        result={"question_ids": ids, "completed_ids": [], "failed_ids": []},
    )
    thread = threading.Thread(
        target=run_explanation_generation_job,
        args=(job.pk,),
        daemon=True,
        name=f"ai-explanation-job-{job.pk}",
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
                            question_type=job.question_type,
                            reference_stem=job.reference_stem or "",
                        ),
                        question_type=job.question_type,
                    )
                    seen_stems = {
                        (v.get("stem") or "").strip().casefold()
                        for v in variations
                        if (v.get("stem") or "").strip()
                    }
                    for item in batch:
                        stem_key = (item.get("stem") or "").strip().casefold()
                        if not stem_key or stem_key in seen_stems:
                            continue
                        seen_stems.add(stem_key)
                        variations.append(item)
                    job.result = {"variations": variations[: job.count]}
                    job.save(update_fields=["result", "updated"])
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
    except Exception:
        logger.exception("AI question job %s crashed", job_id)
        job.status = AIGenerationJob.Status.FAILED
        job.error_message = "Question generation failed. Please try again."
        job.result = {"variations": variations[: job.count]}
        job.save(update_fields=["status", "error_message", "result", "updated"])
    finally:
        close_old_connections()


def _apply_explanation(question: Question, payload: dict) -> bool:
    """Replace explanation steps and optionally seed shared adaptive explanation."""
    from apps.questions.services import (
        adaptive_explanation_has_content,
        clean_adaptive_explanation,
    )

    steps_raw = payload.get("explanation_steps") or []
    summary = (payload.get("solution_summary") or "").strip()
    steps: list[str] = []
    if isinstance(steps_raw, list):
        for item in steps_raw:
            text = str(item).strip()
            if text:
                steps.append(text)
    if not steps and summary:
        steps = [summary]

    applied = False
    if steps and not ExplanationStep.objects.filter(question=question).exists():
        ExplanationStep.objects.bulk_create(
            [
                ExplanationStep(question=question, order=index, content=content)
                for index, content in enumerate(steps, start=1)
            ]
        )
        applied = True
    elif steps and ExplanationStep.objects.filter(question=question).exists():
        applied = True

    update_fields: list[str] = []
    if summary and not (question.concept_tag or "").strip():
        question.concept_tag = summary[:120]
        update_fields.append("concept_tag")

    adaptive = clean_adaptive_explanation(
        {
            "what_went_wrong": payload.get("what_went_wrong"),
            "why": payload.get("why"),
            "quick_check": payload.get("quick_check"),
            "remember": payload.get("remember"),
            "worked_example": payload.get("worked_example"),
        }
    )
    source = (getattr(question, "adaptive_explanation_source", "") or "").strip()
    can_write_adaptive = source != "faculty" and (
        not adaptive_explanation_has_content(question.adaptive_explanation)
    )
    if adaptive_explanation_has_content(adaptive) and can_write_adaptive:
        question.adaptive_explanation = adaptive
        question.adaptive_explanation_source = "ai"
        update_fields.extend(["adaptive_explanation", "adaptive_explanation_source"])
        applied = True

    if update_fields:
        question.save(update_fields=list(dict.fromkeys(update_fields)))

    return applied


def run_explanation_generation_job(job_id: int) -> None:
    close_old_connections()
    try:
        job = AIGenerationJob.objects.get(pk=job_id)
    except AIGenerationJob.DoesNotExist:
        return

    job.status = AIGenerationJob.Status.RUNNING
    job.save(update_fields=["status", "updated"])

    question_ids = list((job.result or {}).get("question_ids") or [])
    completed_ids: list[int] = []
    failed_ids: list[int] = []
    max_attempts = getattr(settings, "AI_GENERATION_MAX_ATTEMPTS", 3)

    try:
        generator = get_explanation_generator()
        questions = (
            Question.objects.filter(pk__in=question_ids)
            .select_related("topic", "topic__subject")
            .prefetch_related("choices", "explanation_steps")
        )
        by_id = {q.pk: q for q in questions}

        for question_id in question_ids:
            question = by_id.get(question_id)
            if question is None:
                failed_ids.append(question_id)
                continue
            if ExplanationStep.objects.filter(question_id=question_id).exists():
                from apps.questions.services import adaptive_explanation_has_content

                if adaptive_explanation_has_content(question.adaptive_explanation):
                    completed_ids.append(question_id)
                    continue

            attempt = 0
            last_exc: AIServiceUnavailableError | None = None
            while attempt < max_attempts:
                try:
                    payload = generator.generate(question)
                    if _apply_explanation(question, payload):
                        completed_ids.append(question_id)
                    else:
                        failed_ids.append(question_id)
                    break
                except AIServiceUnavailableError as exc:
                    last_exc = exc
                    if not exc.retryable:
                        failed_ids.append(question_id)
                        break
                    attempt += 1
                    if attempt < max_attempts:
                        time.sleep(min(2**attempt, 8))
                except Exception:
                    logger.exception(
                        "Explanation generation failed for question %s",
                        question_id,
                    )
                    failed_ids.append(question_id)
                    break
            else:
                if last_exc is not None:
                    failed_ids.append(question_id)

            job.result = {
                "question_ids": question_ids,
                "completed_ids": completed_ids,
                "failed_ids": failed_ids,
            }
            job.save(update_fields=["result", "updated"])

        job.result = {
            "question_ids": question_ids,
            "completed_ids": completed_ids,
            "failed_ids": failed_ids,
        }
        if failed_ids and not completed_ids:
            job.status = AIGenerationJob.Status.FAILED
            job.error_message = "Could not generate explanations. Try again later."
        else:
            job.status = AIGenerationJob.Status.SUCCEEDED
            job.error_message = (
                f"Generated explanations for {len(completed_ids)} question(s)."
                if not failed_ids
                else (
                    f"Generated {len(completed_ids)} explanation(s); "
                    f"{len(failed_ids)} failed."
                )
            )
        job.save(update_fields=["result", "status", "error_message", "updated"])
    except Exception:
        logger.exception("AI explanation job %s crashed", job_id)
        job.status = AIGenerationJob.Status.FAILED
        job.error_message = "Explanation generation failed. Please try again."
        job.result = {
            "question_ids": question_ids,
            "completed_ids": completed_ids,
            "failed_ids": failed_ids,
        }
        job.save(update_fields=["status", "error_message", "result", "updated"])
    finally:
        close_old_connections()

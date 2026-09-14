"""Faculty random question-validation sessions."""

from __future__ import annotations

import random

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.questions.models import (
    Question,
    QuestionValidationItem,
    QuestionValidationSession,
)
from apps.questions.services import publish_question_as_faculty, reject_question


def clamp_validation_size(requested: int | None) -> int:
    default = getattr(settings, "VALIDATION_SESSION_DEFAULT_SIZE", 15)
    lo = getattr(settings, "VALIDATION_SESSION_MIN_SIZE", 10)
    hi = getattr(settings, "VALIDATION_SESSION_MAX_SIZE", 20)
    if requested is None:
        return max(lo, min(hi, default))
    try:
        n = int(requested)
    except (TypeError, ValueError):
        return max(lo, min(hi, default))
    return max(lo, min(hi, n))


@transaction.atomic
def start_validation_session(
    *,
    faculty,
    subject,
    topic=None,
    size: int | None = None,
) -> QuestionValidationSession:
    n = clamp_validation_size(size)
    qs = Question.objects.filter(
        topic__subject=subject,
        status=Question.Status.APPROVED,
        is_active=True,
    )
    if topic is not None:
        qs = qs.filter(topic=topic)
    ids = list(qs.values_list("pk", flat=True))
    if not ids:
        raise ValueError("No approved questions available for validation.")
    sample_ids = random.sample(ids, min(n, len(ids)))
    session = QuestionValidationSession.objects.create(
        faculty=faculty,
        subject=subject,
        topic=topic,
        size=len(sample_ids),
        status=QuestionValidationSession.Status.ACTIVE,
    )
    QuestionValidationItem.objects.bulk_create(
        [
            QuestionValidationItem(session=session, question_id=qid, order=i)
            for i, qid in enumerate(sample_ids)
        ]
    )
    return session


def record_validation_outcome(
    item: QuestionValidationItem,
    *,
    outcome: str,
    notes: str = "",
    faculty=None,
) -> QuestionValidationItem:
    if outcome not in QuestionValidationItem.Outcome.values:
        raise ValueError("Invalid validation outcome.")
    item.outcome = outcome
    item.notes = notes or ""
    item.reviewed_at = timezone.now()
    item.save(update_fields=["outcome", "notes", "reviewed_at"])

    question = item.question
    if outcome == QuestionValidationItem.Outcome.UNPUBLISH and faculty is not None:
        reject_question(question, faculty, note=notes or "Unpublished during validation session.")
    elif outcome == QuestionValidationItem.Outcome.OK and faculty is not None:
        if question.status != Question.Status.APPROVED:
            publish_question_as_faculty(question, faculty)
        elif question.explanation_steps.exists() and question.explanation_status != "faculty_approved":
            from apps.questions.services import approve_question_explanations

            approve_question_explanations(question, faculty)
    return item


def maybe_complete_session(session: QuestionValidationSession) -> QuestionValidationSession:
    pending = session.items.filter(outcome=QuestionValidationItem.Outcome.PENDING).exists()
    if not pending and session.status != QuestionValidationSession.Status.COMPLETED:
        session.status = QuestionValidationSession.Status.COMPLETED
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at"])
    return session

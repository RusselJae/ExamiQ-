"""Retake attempt counting and action-plan gating."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from apps.analytics.models import MistakeRecord
from apps.questions.models import Question
from apps.reviews.models import RetakeActionPlan, ReviewSession


def retake_threshold() -> int:
    return getattr(settings, "RETAKE_ACTION_PLAN_THRESHOLD", 3)


def completed_attempt_count(
    student,
    *,
    course=None,
    subject=None,
    difficulty: str = "",
) -> int:
    qs = ReviewSession.objects.filter(
        student=student,
        status=ReviewSession.Status.COMPLETED,
    )
    if course is not None:
        qs = qs.filter(course=course)
    if subject is not None:
        qs = qs.filter(topic__subject=subject)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    return qs.count()


def requires_action_plan(
    student,
    *,
    course=None,
    subject=None,
    difficulty: str = "",
) -> bool:
    return completed_attempt_count(
        student, course=course, subject=subject, difficulty=difficulty
    ) >= retake_threshold()


def build_action_plan_payload(student, *, course=None, subject=None) -> dict:
    """Assemble recommendations after repeated exam attempts."""
    mistakes = (
        MistakeRecord.objects.filter(student=student)
        .values("topic_id", "topic__name", "question_id")
        .annotate(times=Count("id"))
        .order_by("-times")[:10]
    )
    repeated = [
        {
            "topic_id": row["topic_id"],
            "topic_name": row["topic__name"],
            "question_id": row["question_id"],
            "times": row["times"],
        }
        for row in mistakes
        if row["times"] >= 2
    ]
    materials = []
    if course is not None:
        from apps.ai.material_services import ready_documents_for_course

        for doc in ready_documents_for_course(course.pk)[:5]:
            materials.append(
                {
                    "id": doc.pk,
                    "title": doc.display_title,
                    "material_type": doc.get_material_type_display(),
                }
            )
    question_ids = [r["question_id"] for r in repeated if r.get("question_id")]
    step_links = []
    if question_ids:
        for q in Question.objects.filter(
            pk__in=question_ids,
            explanation_status="faculty_approved",
        ).prefetch_related("explanation_steps")[:5]:
            step_links.append(
                {
                    "question_id": q.pk,
                    "stem": q.stem[:120],
                    "steps": list(q.explanation_steps.values_list("content", flat=True)),
                }
            )
    return {
        "repeated_mistakes": repeated,
        "materials": materials,
        "approved_solutions": step_links,
        "actions": [
            "Review the related learning module or material",
            "Study questions you repeatedly answered incorrectly",
            "Review the faculty-approved step-by-step solutions",
            "Use the AI Tutor for clarification",
            "Complete this action plan before another attempt",
        ],
    }


def get_or_create_action_plan(
    student,
    *,
    course=None,
    subject=None,
    difficulty: str = "",
) -> RetakeActionPlan:
    attempts = completed_attempt_count(
        student, course=course, subject=subject, difficulty=difficulty
    )
    plan = (
        RetakeActionPlan.objects.filter(
            student=student,
            course=course,
            subject=subject,
            difficulty=difficulty or "",
            acknowledged=False,
        )
        .order_by("-created")
        .first()
    )
    payload = build_action_plan_payload(student, course=course, subject=subject)
    if plan is None:
        plan = RetakeActionPlan.objects.create(
            student=student,
            course=course,
            subject=subject,
            difficulty=difficulty or "",
            attempt_count=attempts,
            payload=payload,
        )
    else:
        plan.attempt_count = attempts
        plan.payload = payload
        plan.save(update_fields=["attempt_count", "payload", "modified"])
    return plan


def acknowledge_action_plan(plan: RetakeActionPlan) -> RetakeActionPlan:
    plan.acknowledged = True
    plan.acknowledged_at = timezone.now()
    plan.save(update_fields=["acknowledged", "acknowledged_at", "modified"])
    return plan


def can_start_retake(
    student,
    *,
    course=None,
    subject=None,
    difficulty: str = "",
) -> tuple[bool, RetakeActionPlan | None]:
    """Temporarily allow all retakes (action-plan gate disabled)."""
    return True, None

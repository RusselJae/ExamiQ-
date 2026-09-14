"""Rule-based session summaries and review recommendations."""

from datetime import date, timedelta

from django.db.models import Avg, Count, Max
from django.utils import timezone

from apps.ai.helpers import calibration_narrative_from_matrix
from apps.analytics.confidence import (
    STUDENT_CLASSIFICATION_LABELS,
    avg_confidence_scale_label,
    confidence_accuracy_matrix,
    confidence_from_time_spent,
    confidence_tier_matrix,
)
from apps.analytics.models import MistakeRecord
from apps.questions.models import Topic
from apps.reviews.models import Answer, ReviewSession
from apps.users.models import Course, User


def build_session_summary(session: ReviewSession) -> dict:
    """Build enriched summary for a completed review session."""
    answers = session.answers.all()
    total = answers.count()
    answer_confidences = list(answers.values_list("confidence", flat=True))
    avg_confidence = answers.aggregate(avg=Avg("confidence"))["avg"] or 0
    accuracy = session.accuracy
    calibration_gap = round(avg_confidence * 20 - accuracy, 1) if total else 0
    seconds_per_question = session.seconds_per_question or 30
    time_confidences = [
        confidence_from_time_spent(time_spent or 0, seconds_per_question)
        for time_spent in answers.values_list("time_spent_seconds", flat=True)
    ]

    matrix = confidence_accuracy_matrix(answers)
    tier_matrix = confidence_tier_matrix(answers)
    tier_max = max(tier_matrix.values()) if tier_matrix else 1
    session_mistakes = list(
        MistakeRecord.objects.filter(
            student=session.student,
            answer__session=session,
        )
        .values("topic__name", "topic_id")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:3]
    )
    calibration_rows = [
        {
            "key": key,
            "label": label,
            "count": matrix.get(key, 0),
        }
        for key, label in STUDENT_CLASSIFICATION_LABELS.items()
    ]

    from apps.analytics.services import session_question_trends

    return {
        "total_questions": total,
        "correct_count": session.correct_count,
        "accuracy": accuracy,
        "avg_confidence": round(avg_confidence, 1),
        "avg_confidence_label": avg_confidence_scale_label(answer_confidences),
        "avg_time_confidence_label": avg_confidence_scale_label(time_confidences),
        "calibration_gap": calibration_gap,
        "calibration_matrix": matrix,
        "calibration_rows": calibration_rows,
        "calibration_tier_matrix": tier_matrix,
        "calibration_tier_max": tier_max,
        "narrative": calibration_narrative_from_matrix(matrix, session_mistakes),
        "weak_topics": session_mistakes,
        "question_trends": session_question_trends(session),
    }


def get_review_recommendations(student: User, limit: int = 5) -> list[dict]:
    """Return prioritized topic review recommendations using spaced-repetition rules."""
    if student.role != User.Role.STUDENT or not student.home_degree_program:
        return []

    program_topics = {
        t.pk: t
        for t in Topic.objects.filter(subject__program__slug=student.home_degree_program).select_related(
            "subject__program"
        )
    }
    if not program_topics:
        return []

    topic_ids = list(program_topics.keys())
    today = timezone.localdate()
    recommendations: dict[int, dict] = {}

    for row in (
        MistakeRecord.objects.filter(student=student, topic_id__in=topic_ids)
        .values("topic_id")
        .annotate(mistake_count=Count("id"))
    ):
        tid = row["topic_id"]
        count = row["mistake_count"]
        _upsert_recommendation(
            recommendations,
            tid,
            reason=f"{count} mistakes logged — review this topic",
            priority="high" if count >= 3 else "medium",
            suggested_date=today if count >= 3 else today + timedelta(days=2),
            score=10 if count >= 3 else 6,
        )

    for row in (
        Answer.objects.filter(
            session__student=student,
            question__topic_id__in=topic_ids,
            is_correct=False,
            confidence__gte=4,
        )
        .values("question__topic_id")
        .annotate(count=Count("id"))
    ):
        if row["count"] >= 1:
            _upsert_recommendation(
                recommendations,
                row["question__topic_id"],
                reason="High-confidence wrong answers — confidence gap",
                priority="high",
                suggested_date=today + timedelta(days=1),
                score=12,
            )

    for row in (
        Answer.objects.filter(
            session__student=student,
            question__topic_id__in=topic_ids,
            is_correct=True,
            confidence__lte=2,
        )
        .values("question__topic_id")
        .annotate(count=Count("id"))
    ):
        if row["count"] >= 2:
            _upsert_recommendation(
                recommendations,
                row["question__topic_id"],
                reason="Low-confidence correct answers — reinforce understanding",
                priority="medium",
                suggested_date=today + timedelta(days=2),
                score=7,
            )

    for row in (
        Answer.objects.filter(
            session__student=student,
            question__topic_id__in=topic_ids,
            is_correct=False,
        )
        .values("question__topic_id")
        .annotate(count=Count("id"))
    ):
        _upsert_recommendation(
            recommendations,
            row["question__topic_id"],
            reason="Recent wrong answers — practice again",
            priority="medium",
            suggested_date=today + timedelta(days=2),
            score=5,
        )

    last_by_topic = {
        row["topic_id"]: row["last_date"].date()
        for row in ReviewSession.objects.filter(student=student, topic_id__in=topic_ids)
        .values("topic_id")
        .annotate(last_date=Max("started_at"))
    }

    course = (
        Course.objects.filter(program__slug=student.home_degree_program, is_archived=False)
        .order_by("-academic_year", "term", "code")
        .first()
    )

    results = []
    for tid, rec in sorted(recommendations.items(), key=lambda x: (-x[1]["score"], x[1]["suggested_date"])):
        topic = program_topics.get(tid)
        if not topic:
            continue
        last = last_by_topic.get(tid)
        results.append(
            {
                "topic": topic,
                "topic_name": topic.name,
                "reason": rec["reason"],
                "priority": rec["priority"],
                "suggested_date": rec["suggested_date"],
                "is_due": rec["suggested_date"] <= today,
                "course": course,
                "days_since_review": (today - last).days if last else None,
            }
        )
        if len(results) >= limit:
            break

    return results


def _upsert_recommendation(
    store: dict,
    topic_id: int,
    reason: str,
    priority: str,
    suggested_date: date,
    score: int,
) -> None:
    existing = store.get(topic_id)
    if existing and existing["score"] >= score:
        return
    store[topic_id] = {
        "reason": reason,
        "priority": priority,
        "suggested_date": suggested_date,
        "score": score,
    }

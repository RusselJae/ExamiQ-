"""Concept-level remediation: Learn → Try it → Practice (no timer)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, QuerySet
from django.utils import timezone

from apps.analytics.models import ConceptPracticeAttempt, ConceptReview, MistakeRecord
from apps.questions.models import Question
from apps.reviews.models import Answer
from apps.users.models import User

CORRECT_TO_RESOLVE = 3
RECHECK_DAYS = 7
FEEDBACK_STYLES = (
    "worked_example",
    "analogy",
    "mistakes_first",
    "backwards",
)
STATUS_NEEDS = ConceptReview.Status.NEEDS_REVIEW
STATUS_PRACTICING = ConceptReview.Status.PRACTICING
STATUS_RESOLVED = ConceptReview.Status.RESOLVED


def concept_key_for_question(question: Question) -> tuple[str, str]:
    """Return (concept_key, concept_name) for a question."""
    tag = (question.concept_tag or "").strip()
    if tag:
        return tag.casefold(), tag
    topic = question.topic
    return f"topic:{topic.pk}", topic.name


def _confidence_bucket(confidence: int | None) -> str:
    if confidence is None:
        return ""
    if confidence >= 4:
        return "sure"
    return "guessing"


def _wrong_answer_text(answer: Answer) -> str:
    if answer.selected_choice_id:
        return (answer.selected_choice.text or "").strip()[:500]
    return (answer.numeric_response or "").strip()[:500]


def record_exam_miss_for_concept(
    student: User,
    question: Question,
    answer: Answer,
    *,
    error_slug: str = "",
) -> ConceptReview:
    """Upsert a ConceptReview when the student misses a question in an exam."""
    key, name = concept_key_for_question(question)
    topic = question.topic
    wrong_text = _wrong_answer_text(answer)
    bucket = _confidence_bucket(answer.confidence)
    raw_diff = (getattr(question, "difficulty", None) or "").lower()
    difficulty = {
        "easy": "beginner",
        "medium": "intermediate",
        "hard": "advanced",
        "beginner": "beginner",
        "intermediate": "intermediate",
        "advanced": "advanced",
    }.get(raw_diff, "beginner")

    review, created = ConceptReview.objects.get_or_create(
        student=student,
        concept_key=key,
        defaults={
            "concept_name": name,
            "topic": topic,
            "status": STATUS_NEEDS,
            "current_step": ConceptReview.Step.LEARN,
            "miss_count": 1,
            "same_wrong_answer_count": 1 if wrong_text else 0,
            "marked_sure_count": 1 if bucket == "sure" else 0,
            "marked_guessing_count": 1 if bucket == "guessing" else 0,
            "last_wrong_answer_text": wrong_text,
            "difficulty": difficulty,
            "known_error_tags": [error_slug] if error_slug else [],
        },
    )
    if created:
        return review

    review.concept_name = name
    review.topic = topic
    review.miss_count += 1
    if wrong_text:
        if (
            review.last_wrong_answer_text
            and wrong_text.casefold() == review.last_wrong_answer_text.casefold()
        ):
            review.same_wrong_answer_count += 1
        elif not review.last_wrong_answer_text:
            review.same_wrong_answer_count = 1
        else:
            review.same_wrong_answer_count = 1
        review.last_wrong_answer_text = wrong_text
    if bucket == "sure":
        review.marked_sure_count += 1
    elif bucket == "guessing":
        review.marked_guessing_count += 1

    tags = list(review.known_error_tags or [])
    if error_slug and error_slug not in tags:
        tags.append(error_slug)
        review.known_error_tags = tags

    if review.status == STATUS_RESOLVED:
        review.status = STATUS_NEEDS
        review.current_step = ConceptReview.Step.LEARN
        review.correct_streak = 0
        review.resolved_at = None
        review.recheck_due_at = None
        review.learn_payload = {}
    elif review.status == STATUS_PRACTICING:
        pass
    else:
        review.status = STATUS_NEEDS

    review.difficulty = difficulty
    review.save()
    return review


def list_concept_reviews(
    student: User,
    *,
    status: str | None = None,
) -> QuerySet[ConceptReview]:
    """Return concept reviews for the student, optionally filtered by status."""
    qs = (
        ConceptReview.objects.filter(student=student)
        .select_related("topic", "topic__subject")
        .annotate(open_attempts=Count("practice_attempts"))
    )
    if status and status in {s.value for s in ConceptReview.Status}:
        qs = qs.filter(status=status)
    return qs


def concept_status_counts(student: User) -> dict[str, int]:
    """Return counts per status for chip badges."""
    rows = (
        ConceptReview.objects.filter(student=student)
        .values("status")
        .annotate(c=Count("id"))
    )
    counts = {s.value: 0 for s in ConceptReview.Status}
    for row in rows:
        counts[row["status"]] = row["c"]
    counts["active"] = counts[STATUS_NEEDS] + counts[STATUS_PRACTICING]
    return counts


def build_concept_card_context(review: ConceptReview) -> dict[str, Any]:
    """Template-friendly card fields for the Concepts to Review list."""
    parts: list[str] = [f"Missed {review.miss_count} time" + ("s" if review.miss_count != 1 else "")]
    if review.same_wrong_answer_count >= 2:
        parts.append(
            f"Same wrong answer picked {review.same_wrong_answer_count} times"
            if review.same_wrong_answer_count > 2
            else "Same wrong answer picked twice"
        )
    if review.marked_sure_count and not review.marked_guessing_count:
        parts.append("Marked Sure.")
    elif review.marked_guessing_count and not review.marked_sure_count:
        parts.append("Marked Guessing.")
    elif review.marked_sure_count:
        parts.append("Marked Sure.")

    if review.status == STATUS_PRACTICING and review.correct_streak:
        parts.append(
            f"Passed {review.correct_streak} untimed question"
            + ("s" if review.correct_streak != 1 else "")
            + "."
        )

    badge = "Needs Review"
    badge_class = "needs-review"
    if review.diagnosis_type == ConceptReview.DiagnosisType.MISCONCEPTION:
        badge = "Likely misconception"
        badge_class = "misconception"
    elif review.diagnosis_type == ConceptReview.DiagnosisType.KNOWLEDGE_GAP:
        badge = "Knowledge gap"
        badge_class = "knowledge-gap"
    elif review.status == STATUS_PRACTICING:
        badge = "Practicing"
        badge_class = "practicing"
    elif review.status == STATUS_RESOLVED:
        badge = "Resolved"
        badge_class = "resolved"

    subject = review.topic.subject if review.topic_id else None
    subject_label = ""
    if subject:
        subject_label = f"{subject.name} · {subject.code}" if subject.code else subject.name

    cta = "Start review"
    if review.status == STATUS_PRACTICING:
        cta = "Continue practice"
    elif review.status == STATUS_RESOLVED:
        cta = "Review again"

    return {
        "review": review,
        "badge": badge,
        "badge_class": badge_class,
        "miss_blurb": " · ".join(parts),
        "subject_label": subject_label,
        "progress_label": f"{review.correct_streak} of {CORRECT_TO_RESOLVE} correct",
        "cta": cta,
        "progress_pct": int(100 * review.correct_streak / CORRECT_TO_RESOLVE),
    }


def _pick_feedback_style(used: list[str]) -> str:
    used_set = {str(s) for s in (used or [])}
    for style in FEEDBACK_STYLES:
        if style not in used_set:
            return style
    return FEEDBACK_STYLES[0]


def _infer_student_stage(review: ConceptReview) -> str:
    if review.miss_count >= 4 or len(review.feedback_styles_used or []) >= 2:
        return "remediation"
    if review.feedback_styles_used:
        return "second_review"
    return "first_review"


def _missed_questions_payload(review: ConceptReview) -> list[dict[str, Any]]:
    key = review.concept_key
    records = (
        MistakeRecord.objects.filter(student=review.student)
        .select_related(
            "question",
            "answer",
            "answer__selected_choice",
            "question__topic",
        )
        .order_by("-occurred_at")[:8]
    )
    items: list[dict[str, Any]] = []
    for record in records:
        q_key, _ = concept_key_for_question(record.question)
        if q_key != key:
            continue
        chosen = _wrong_answer_text(record.answer)
        correct = ""
        if record.question.question_type == Question.QuestionType.MCQ:
            correct_choice = record.question.choices.filter(is_correct=True).first()
            if correct_choice:
                correct = correct_choice.text
        else:
            correct = record.question.expected_answer or ""
        conf = _confidence_bucket(record.answer.confidence)
        conf_label = "Sure" if conf == "sure" else "Guessing" if conf == "guessing" else ""
        items.append(
            {
                "stem": record.question.stem,
                "chosen_answer": chosen,
                "correct_answer": correct,
                "confidence": conf_label,
            }
        )
    return items


def ensure_learn_content(review: ConceptReview, *, force: bool = False) -> ConceptReview:
    """Generate and cache Learn / Try it content when missing."""
    if review.learn_payload and not force:
        return review

    from apps.ai.factory import get_concept_remediation_generator

    style = _pick_feedback_style(list(review.feedback_styles_used or []))
    generator = get_concept_remediation_generator()
    payload = generator.generate(
        concept_name=review.concept_name,
        subject=(review.topic.subject.name if review.topic.subject_id else ""),
        topic=review.topic.name,
        difficulty=review.difficulty or "beginner",
        miss_count=review.miss_count,
        missed_questions=_missed_questions_payload(review),
        previous_feedback_styles=list(review.feedback_styles_used or []),
        student_stage=_infer_student_stage(review),
        prerequisites=[],
        preferred_style=style,
    )
    if not isinstance(payload, dict):
        payload = {}

    review.learn_payload = payload
    diagnosis = payload.get("diagnosis") or {}
    dtype = (diagnosis.get("type") or "").strip()
    if dtype in {c.value for c in ConceptReview.DiagnosisType}:
        review.diagnosis_type = dtype
    prereq = diagnosis.get("prerequisite_flag")
    if prereq and str(prereq).strip().lower() not in {"", "null", "none"}:
        review.prerequisite_flag = str(prereq).strip()
        review.prerequisite_mode = True
    else:
        review.prerequisite_flag = ""
        review.prerequisite_mode = False

    styles = list(review.feedback_styles_used or [])
    used_style = (payload.get("explanation") or {}).get("style_used") or style
    if used_style not in styles:
        styles.append(used_style)
        review.feedback_styles_used = styles

    if review.status == STATUS_NEEDS:
        review.status = STATUS_NEEDS
    review.current_step = ConceptReview.Step.LEARN
    review.save()
    return review


def advance_to_try_it(review: ConceptReview) -> ConceptReview:
    ensure_learn_content(review)
    review.current_step = ConceptReview.Step.TRY_IT
    if review.status == STATUS_NEEDS:
        review.status = STATUS_PRACTICING
    review.save(update_fields=["current_step", "status", "updated_at"])
    return review


def submit_try_it(
    review: ConceptReview,
    choice_index: int,
) -> dict[str, Any]:
    """Score the Try it first-step choice against cached payload."""
    ensure_learn_content(review)
    try_it = review.try_it_payload
    choices = try_it.get("first_step_choices") or []
    correct_index = int(try_it.get("correct_index") or 0)
    hint = try_it.get("hint") or ""
    feedback_if_wrong = try_it.get("feedback_if_wrong") or "Not quite. Try again."

    is_correct = choice_index == correct_index
    result = {
        "is_correct": is_correct,
        "correct_index": correct_index,
        "hint": hint,
        "feedback": "" if is_correct else feedback_if_wrong,
        "choices": choices,
    }
    if is_correct:
        review.current_step = ConceptReview.Step.PRACTICE
        if review.status != STATUS_RESOLVED:
            review.status = STATUS_PRACTICING
        review.save(update_fields=["current_step", "status", "updated_at"])
    return result


def _previous_practice_questions(review: ConceptReview) -> list[dict[str, Any]]:
    attempts = review.practice_attempts.order_by("attempt_number")
    out: list[dict[str, Any]] = []
    for attempt in attempts:
        payload = attempt.question_payload or {}
        if payload.get("question"):
            out.append(
                {
                    "question": payload.get("question"),
                    "final_answer": payload.get("final_answer"),
                    "options": [
                        o.get("text")
                        for o in (payload.get("options") or [])
                        if isinstance(o, dict)
                    ],
                }
            )
    return out


def start_or_next_practice(review: ConceptReview) -> ConceptPracticeAttempt:
    """Return an unanswered practice attempt, creating one via AI if needed."""
    open_attempt = (
        review.practice_attempts.filter(is_correct__isnull=True)
        .order_by("-attempt_number")
        .first()
    )
    if open_attempt:
        return open_attempt

    from apps.ai.factory import get_concept_practice_generator

    attempt_number = review.practice_attempts.count() + 1
    concept_name = review.concept_name
    if review.prerequisite_mode and review.prerequisite_flag:
        concept_name = review.prerequisite_flag

    generator = get_concept_practice_generator()
    payload = generator.generate(
        concept_name=concept_name,
        subject=(review.topic.subject.name if review.topic.subject_id else ""),
        topic=review.topic.name,
        difficulty=review.difficulty or "beginner",
        attempt_number=attempt_number,
        known_error_tags=list(review.known_error_tags or []),
        previous_questions=_previous_practice_questions(review),
        prerequisite_mode=bool(review.prerequisite_mode and review.prerequisite_flag),
        prerequisite_concept=review.prerequisite_flag or "",
    )
    if not isinstance(payload, dict):
        payload = {}

    # Merge known error tags seen in distractors for future practice.
    tags = list(review.known_error_tags or [])
    for opt in payload.get("options") or []:
        if not isinstance(opt, dict) or opt.get("is_correct"):
            continue
        tag = (opt.get("error_tag") or "").strip()
        if tag and tag not in tags:
            tags.append(tag)
    review.known_error_tags = tags
    review.current_step = ConceptReview.Step.PRACTICE
    if review.status != STATUS_RESOLVED:
        review.status = STATUS_PRACTICING
    review.last_practiced_at = timezone.now()
    review.save(
        update_fields=[
            "known_error_tags",
            "current_step",
            "status",
            "last_practiced_at",
            "updated_at",
        ]
    )

    return ConceptPracticeAttempt.objects.create(
        concept_review=review,
        attempt_number=attempt_number,
        question_payload=payload,
    )


def submit_practice_answer(
    review: ConceptReview,
    attempt: ConceptPracticeAttempt,
    option_id: str,
) -> dict[str, Any]:
    """Grade a practice attempt; resolve after 3 correct (hold streak on wrong)."""
    payload = attempt.question_payload or {}
    options = payload.get("options") or []
    chosen = None
    correct = None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        if opt.get("is_correct"):
            correct = opt
        if str(opt.get("id", "")).upper() == str(option_id).upper():
            chosen = opt

    is_correct = bool(chosen and chosen.get("is_correct"))
    error_tag = ""
    why_wrong = ""
    if chosen and not is_correct:
        error_tag = (chosen.get("error_tag") or "").strip()
        why_wrong = (chosen.get("why_wrong") or "").strip()
        if error_tag:
            tags = list(review.known_error_tags or [])
            if error_tag not in tags:
                tags.append(error_tag)
                review.known_error_tags = tags

    attempt.chosen_option_id = str(option_id).upper()[:8]
    attempt.is_correct = is_correct
    attempt.error_tag_hit = error_tag
    attempt.answered_at = timezone.now()
    attempt.save(
        update_fields=[
            "chosen_option_id",
            "is_correct",
            "error_tag_hit",
            "answered_at",
        ]
    )

    resolved = False
    if is_correct:
        # Count distinct correct questions in the current open cycle.
        correct_count = review.practice_attempts.filter(is_correct=True).count()
        review.correct_streak = min(correct_count, CORRECT_TO_RESOLVE)
        if review.correct_streak >= CORRECT_TO_RESOLVE:
            review.status = STATUS_RESOLVED
            review.resolved_at = timezone.now()
            review.recheck_due_at = review.resolved_at + timedelta(days=RECHECK_DAYS)
            resolved = True
        else:
            review.status = STATUS_PRACTICING
    else:
        # Hold streak (do not reset) per plan.
        review.status = STATUS_PRACTICING

    review.last_practiced_at = timezone.now()
    review.save()

    return {
        "is_correct": is_correct,
        "resolved": resolved,
        "correct_streak": review.correct_streak,
        "why_wrong": why_wrong,
        "error_tag": error_tag,
        "hint": payload.get("hint") or "",
        "solution_steps": payload.get("solution_steps") or [],
        "final_answer": payload.get("final_answer") or "",
        "self_check": payload.get("self_check") or "",
        "correct_option_id": (correct or {}).get("id") if correct else None,
    }


def restart_concept_review(review: ConceptReview) -> ConceptReview:
    """Clear teach cache and restart Learn (Review again)."""
    review.status = STATUS_NEEDS
    review.current_step = ConceptReview.Step.LEARN
    review.correct_streak = 0
    review.resolved_at = None
    review.recheck_due_at = None
    review.learn_payload = {}
    review.prerequisite_mode = False
    review.prerequisite_flag = ""
    review.save()
    # Keep practice history for previous_questions context; do not delete.
    return review


def miss_history_for_sidebar(review: ConceptReview) -> list[dict[str, str]]:
    """Short history lines for the Learn side panel."""
    items = _missed_questions_payload(review)[:5]
    lines: list[dict[str, str]] = []
    records = (
        MistakeRecord.objects.filter(student=review.student)
        .select_related("answer", "answer__selected_choice", "question")
        .order_by("-occurred_at")[:12]
    )
    for record in records:
        q_key, _ = concept_key_for_question(record.question)
        if q_key != review.concept_key:
            continue
        chosen = _wrong_answer_text(record.answer)
        conf = _confidence_bucket(record.answer.confidence)
        conf_label = "Sure" if conf == "sure" else "Guessing" if conf == "guessing" else ""
        date_str = record.occurred_at.strftime("%b %d")
        detail = f"picked {chosen}" if chosen else "missed"
        if conf_label:
            detail = f"{detail}, marked {conf_label}"
        lines.append({"date": date_str, "detail": detail})
        if len(lines) >= 5:
            break
    return lines or [
        {"date": "", "detail": item.get("chosen_answer") or "Missed"} for item in items[:3]
    ]


def diagnose_from_stats(review: ConceptReview) -> str:
    """Heuristic diagnosis before AI teach runs (for card badges)."""
    if review.same_wrong_answer_count >= 2 or review.marked_sure_count >= 2:
        return ConceptReview.DiagnosisType.MISCONCEPTION
    if review.marked_guessing_count >= review.miss_count // 2 and review.miss_count >= 2:
        return ConceptReview.DiagnosisType.KNOWLEDGE_GAP
    return ConceptReview.DiagnosisType.KNOWLEDGE_GAP

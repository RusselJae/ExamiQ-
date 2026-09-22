"""Analytics and performance aggregation services."""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek, TruncYear

from apps.analytics.confidence import (
    CLASSIFICATION_LABELS,
    PACE_BAR_COUNTS,
    PACE_QUICK,
    answer_is_unanswered,
    confidence_accuracy_matrix,
    confidence_tier_matrix,
    misconception_topics,
    pace_from_answer,
)
from apps.analytics.models import MistakeRecord
from apps.questions.models import Question, Subject, Topic
from apps.reviews.models import Answer, FeedbackView, ReviewSession
from apps.users.constants import home_programs_for_department, students_in_department
from apps.reviews.tutor_services import (
    format_answer_user_text,
    format_question_correct_text,
)
from apps.users.models import Course, Program, User


def log_mistake(
    student: User,
    question: Question,
    answer: Answer,
    *,
    generate_ai: bool = False,
) -> MistakeRecord:
    """Create a mistake record when a student answers incorrectly."""
    from apps.questions.services import (
        distinct_student_mistake_count,
        mistake_student_threshold,
    )

    error_type = None
    if answer.selected_choice_id and answer.selected_choice.error_type_id:
        error_type = answer.selected_choice.error_type

    prior_unique = distinct_student_mistake_count(question)
    already_counted = question.mistake_records.filter(student=student).exists()

    ai_feedback = ""
    record = MistakeRecord.objects.create(
        student=student,
        question=question,
        topic=question.topic,
        answer=answer,
        error_type=error_type,
        ai_feedback=ai_feedback,
    )
    if generate_ai:
        generate_mistake_feedback(record)
        record.refresh_from_db()

    threshold = mistake_student_threshold()
    unique_after = prior_unique if already_counted else prior_unique + 1
    if unique_after >= threshold and prior_unique < threshold:
        notify_faculty_mistake_threshold(question)

    return record


def notify_faculty_mistake_threshold(question: Question) -> None:
    """Notify faculty when distinct-student mistakes cross the revision threshold."""
    from django.urls import reverse

    from apps.questions.services import mistake_student_threshold
    from apps.users.assignment_services import get_or_create_catalog_course
    from apps.users.models import Course, Notification, TeachingAssignment, User
    from apps.users.notification_services import create_notification

    subject = question.topic.subject
    threshold = mistake_student_threshold()
    message = f"{subject.code}: {threshold}+ students missed a question — revise it"

    recipients: dict[int, tuple[User, Course]] = {}

    for course in Course.objects.filter(
        code=subject.code,
        program=subject.program,
        is_archived=False,
        professor__isnull=False,
    ).select_related("professor"):
        professor = course.professor
        if professor and professor.role == User.Role.PROFESSOR:
            recipients[professor.pk] = (professor, course)

    for assignment in TeachingAssignment.objects.filter(subject=subject).select_related(
        "professor"
    ):
        professor = assignment.professor
        if (
            not professor
            or professor.role != User.Role.PROFESSOR
            or professor.pk in recipients
        ):
            continue
        course = get_or_create_catalog_course(professor, subject)
        recipients[professor.pk] = (professor, course)

    for professor, course in recipients.values():
        link = reverse(
            "analytics_professor:question_edit",
            kwargs={"course_pk": course.pk, "question_pk": question.pk},
        )
        if Notification.objects.filter(
            user=professor, link=link, read_at__isnull=True
        ).exists():
            continue
        create_notification(professor, message, link=link)


def _question_choice_labels(question) -> list[str]:
    """Format MCQ options as 'A: text' lines for the adaptive feedback prompt."""
    choices = list(question.choices.order_by("label"))
    if not choices:
        return []
    return [f"{c.label}: {c.text}" for c in choices]


def generate_mistake_feedback(mistake_record: MistakeRecord) -> str:
    """Generate and persist AI feedback for an existing mistake record."""
    answer = mistake_record.answer
    question = mistake_record.question

    if not mistake_record.error_type_id and answer.selected_choice_id:
        from apps.ai.factory import get_error_classifier

        error_type = get_error_classifier().classify(question, answer)
        if error_type:
            mistake_record.error_type = error_type
            mistake_record.save(update_fields=["error_type"])

    from apps.questions.services import faculty_adaptive_feedback_json

    faculty_feedback = faculty_adaptive_feedback_json(question)
    if faculty_feedback:
        mistake_record.ai_feedback = faculty_feedback
        mistake_record.save(update_fields=["ai_feedback"])
        return faculty_feedback

    ai_feedback = ""
    try:
        from django.conf import settings

        if settings.AI_ENABLED:
            from apps.ai.factory import get_adaptive_feedback_generator
            from apps.ai.normalize import (
                adaptive_feedback_to_json,
                validate_adaptive_feedback,
            )
            from apps.analytics.confidence import answer_is_unanswered

            user_answer = format_answer_user_text(answer)
            correct_answer = format_question_correct_text(question)

            confidence = "medium"
            if answer.confidence is not None:
                if answer.confidence <= 2:
                    confidence = "low"
                elif answer.confidence >= 4:
                    confidence = "high"

            ai_feedback = get_adaptive_feedback_generator().generate(
                topic=question.topic.name,
                question=question.stem,
                user_answer=user_answer or "No answer",
                correct_answer=correct_answer or "Unknown",
                confidence=confidence,
                question_type=question.get_question_type_display(),
                choices=_question_choice_labels(question),
                difficulty=question.get_difficulty_display(),
                is_correct=False,
                unanswered=answer_is_unanswered(answer),
            )
            validated = validate_adaptive_feedback(ai_feedback)
            if validated:
                ai_feedback = adaptive_feedback_to_json(validated)
    except Exception:
        ai_feedback = ""

    if ai_feedback:
        from apps.ai.normalize import normalize_feedback_text, validate_adaptive_feedback

        # Keep structured JSON when valid; otherwise store plain text.
        if not validate_adaptive_feedback(ai_feedback):
            ai_feedback = normalize_feedback_text(ai_feedback)
        mistake_record.ai_feedback = ai_feedback
        mistake_record.save(update_fields=["ai_feedback"])
    return ai_feedback


def _explanation_steps_text(question) -> str:
    """Join approved explanation steps for display feedback."""
    lines = list(question.explanation_steps.order_by("order").values_list("content", flat=True))
    return "\n".join(lines) if lines else ""


def _type_specific_incorrect_feedback(answer: Answer) -> str:
    """Fallback explanation when no explanation steps exist."""
    question = answer.question
    user = format_answer_user_text(answer)
    correct = format_question_correct_text(question)
    qtype = question.question_type

    if qtype == Question.QuestionType.MCQ:
        return (
            f"You chose {user}, but the correct answer is {correct}. "
            "Review why the other options are incorrect."
        )
    if qtype == Question.QuestionType.TRUE_FALSE:
        return (
            f"This statement is {correct}. You answered {user}. "
            "Re-read the claim and decide whether it is true or false."
        )
    if qtype == Question.QuestionType.IDENTIFICATION:
        return (
            f"The expected answer is {correct}. You wrote {user}. "
            "Check spelling and the key term the question is asking for."
        )
    if qtype == Question.QuestionType.ENUMERATION:
        return (
            f"The complete answer should include:\n{correct}\n\n"
            f"You submitted:\n{user}\n\n"
            "List every required item — one per line."
        )
    if qtype == Question.QuestionType.NUMERIC:
        return (
            f"The correct value is {correct}. You entered {user}. "
            "Review your calculation step by step."
        )
    return f"The correct answer is {correct}. You answered {user}."


def _rule_based_answer_feedback(answer) -> str:
    """Fast fallback feedback using explanation steps or generic guidance."""
    steps_text = _explanation_steps_text(answer.question)
    if answer.is_correct:
        if steps_text:
            return f"Correct! {steps_text}"
        return "Correct answer. Keep practicing to reinforce this topic."

    if answer.timed_out:
        if steps_text:
            return f"Time ran out on this question.\n\n{steps_text}"
        return "Time ran out on this question. Review the solution and try similar problems."

    if steps_text:
        return steps_text

    return _type_specific_incorrect_feedback(answer)


def _get_answer_mistake_record(answer):
    """Return mistake record for an answer, or None when the answer was correct."""
    try:
        return answer.mistake_record
    except ObjectDoesNotExist:
        return None


def get_answer_feedback_quick(answer) -> tuple[str, bool]:
    """Return cached/rule feedback quickly without calling the LLM.

    Second value is True when AI enrichment should be requested later.
    """
    from django.conf import settings

    from apps.ai.normalize import (
        normalize_feedback_text,
        parse_any_adaptive_feedback,
        validate_adaptive_feedback,
        validate_correct_adaptive_feedback,
    )
    from apps.questions.services import faculty_adaptive_feedback_json

    faculty_feedback = faculty_adaptive_feedback_json(answer.question)
    if faculty_feedback and not answer.is_correct:
        return faculty_feedback, False

    mistake_record = _get_answer_mistake_record(answer)
    if mistake_record and mistake_record.ai_feedback:
        raw = mistake_record.ai_feedback
        # Preserve structured JSON for the tutor UI when present.
        if validate_adaptive_feedback(raw):
            return raw, False
        return normalize_feedback_text(raw), False

    # Correct answers cache structured JSON on Answer.ai_feedback.
    cached = (getattr(answer, "ai_feedback", None) or "").strip()
    if cached:
        if validate_correct_adaptive_feedback(cached) or validate_adaptive_feedback(
            cached
        ):
            return cached, False
        if parse_any_adaptive_feedback(cached):
            return cached, False
        return normalize_feedback_text(cached), False

    rule = _rule_based_answer_feedback(answer)
    needs_ai = bool(settings.AI_ENABLED)
    return rule, needs_ai


def generate_answer_feedback(answer) -> str:
    """Generate and return feedback for a session answer."""
    from apps.ai.normalize import (
        adaptive_feedback_to_json,
        correct_adaptive_feedback_to_json,
        normalize_feedback_text,
        validate_adaptive_feedback,
        validate_correct_adaptive_feedback,
    )
    from apps.analytics.confidence import answer_is_unanswered
    from apps.questions.services import faculty_adaptive_feedback_json

    faculty_feedback = faculty_adaptive_feedback_json(answer.question)
    if faculty_feedback and not answer.is_correct:
        return faculty_feedback

    mistake_record = _get_answer_mistake_record(answer)
    if mistake_record and mistake_record.ai_feedback:
        raw = mistake_record.ai_feedback
        if validate_adaptive_feedback(raw):
            return raw
        return normalize_feedback_text(raw)

    cached = (getattr(answer, "ai_feedback", None) or "").strip()
    if cached:
        if validate_correct_adaptive_feedback(cached) or validate_adaptive_feedback(
            cached
        ):
            return cached
        return normalize_feedback_text(cached)

    if mistake_record:
        try:
            ai_feedback = generate_mistake_feedback(mistake_record)
            if ai_feedback:
                if validate_adaptive_feedback(ai_feedback):
                    return ai_feedback
                return normalize_feedback_text(ai_feedback)
        except Exception:
            pass
        return _rule_based_answer_feedback(answer)

    from django.conf import settings

    if not settings.AI_ENABLED:
        return _rule_based_answer_feedback(answer)

    try:
        from apps.ai.factory import get_adaptive_feedback_generator

        question = answer.question
        user_answer = format_answer_user_text(answer)
        correct_answer = format_question_correct_text(question)
        unanswered = answer_is_unanswered(answer)
        is_correct = bool(answer.is_correct) and not unanswered

        confidence = "high" if answer.confidence and answer.confidence >= 4 else "medium"
        ai_feedback = get_adaptive_feedback_generator().generate(
            topic=question.topic.name,
            question=question.stem,
            user_answer=user_answer or "No answer",
            correct_answer=correct_answer or "Unknown",
            confidence=confidence,
            question_type=question.get_question_type_display(),
            choices=_question_choice_labels(question),
            difficulty=question.get_difficulty_display(),
            is_correct=is_correct,
            unanswered=unanswered,
        )
        if ai_feedback:
            if is_correct:
                validated = validate_correct_adaptive_feedback(ai_feedback)
                if validated:
                    stored = correct_adaptive_feedback_to_json(validated)
                    Answer.objects.filter(pk=answer.pk).update(ai_feedback=stored)
                    answer.ai_feedback = stored
                    return stored
                return normalize_feedback_text(ai_feedback)

            validated = validate_adaptive_feedback(ai_feedback)
            if validated:
                stored = adaptive_feedback_to_json(validated)
                # Incorrect without a MistakeRecord still persists on the answer.
                Answer.objects.filter(pk=answer.pk).update(ai_feedback=stored)
                answer.ai_feedback = stored
                return stored
            return normalize_feedback_text(ai_feedback)
    except Exception:
        pass

    return _rule_based_answer_feedback(answer)


def generate_session_feedback(session) -> list[dict]:
    """Generate feedback for every answer in a completed session."""
    from apps.analytics.confidence import answer_is_unanswered, confidence_tier_key
    from apps.ai.normalize import parse_any_adaptive_feedback

    results = []
    answers = (
        session.answers.select_related("question", "selected_choice", "mistake_record")
        .prefetch_related("question__choices")
        .order_by("answered_at")
    )
    for answer in answers:
        feedback = generate_answer_feedback(answer)
        tier_key = confidence_tier_key(answer.confidence)
        unanswered = answer_is_unanswered(answer)
        results.append(
            {
                "answer_id": answer.pk,
                "stem": answer.question.stem,
                "is_correct": bool(answer.is_correct) and not unanswered,
                "timed_out": answer.timed_out,
                "unanswered": unanswered,
                "no_selection": unanswered,
                "confidence_tier": tier_key,
                "feedback": feedback,
                "structured_feedback": parse_any_adaptive_feedback(feedback),
            }
        )
    return results


def student_performance_summary(student: User) -> dict:
    """Return performance summary for a single student."""
    sessions = ReviewSession.objects.filter(
        student=student,
        status=ReviewSession.Status.COMPLETED,
    )
    answers = Answer.objects.filter(session__student=student)

    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    avg_confidence = answers.aggregate(avg=Avg("confidence"))["avg"] or 0

    accuracy_trend = list(
        sessions.annotate(date=TruncDate("started_at"))
        .values("date")
        .annotate(
            total=Count("answers"),
            correct=Count("answers", filter=Q(answers__is_correct=True)),
        )
        .order_by("date")
    )
    for item in accuracy_trend:
        total = item["total"]
        item["accuracy"] = round(item["correct"] / total * 100, 1) if total else 0

    weak_topics = list(
        MistakeRecord.objects.filter(student=student)
        .values("topic__name")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:5]
    )

    recent_sessions = annotate_session_metrics(
        sessions.select_related("topic").order_by("-started_at")[:10]
    )

    return {
        "sessions_completed": sessions.count(),
        "total_answers": total_answers,
        "accuracy": accuracy,
        "avg_confidence": round(avg_confidence, 1),
        "accuracy_trend": accuracy_trend,
        "weak_topics": weak_topics,
        "recent_sessions": recent_sessions,
        "recent_session_rows": build_session_history_rows(recent_sessions),
    }


def _ordinal_label(n: int) -> str:
    """Return 1st, 2nd, 3rd, 4th, …"""
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def student_dashboard_trends(student: User) -> dict:
    """Flat confidence trend series for the student dashboard.

    Stacked Sure / Not sure / Guessing / No ratings shares per session
    plus correct_pct for the accuracy overlay.
    """
    from django.utils import timezone

    sessions = list(
        annotate_session_metrics(
            ReviewSession.objects.filter(
                student=student,
                status=ReviewSession.Status.COMPLETED,
            )
            .select_related("topic")
            .order_by("started_at", "id")
        )
    )
    session_ids = [s.pk for s in sessions]
    answers_by_session: dict[int, list] = {sid: [] for sid in session_ids}
    if session_ids:
        for answer in Answer.objects.filter(session_id__in=session_ids).only(
            "session_id", "confidence", "is_correct"
        ):
            answers_by_session.setdefault(answer.session_id, []).append(answer)

    confidence_points = []
    for index, session in enumerate(sessions, start=1):
        ordinal = _ordinal_label(index)
        if session.started_at:
            date_part = timezone.localtime(session.started_at).strftime("%m-%d-%Y")
            label = f"{ordinal} ({date_part})"
        else:
            label = ordinal
        session_answers = answers_by_session.get(session.pk, [])
        confidence_points.append(_confidence_share_point(label, session_answers))

    return {
        "confidence": confidence_points,
        "confidence_insight": build_confidence_insight(confidence_points),
    }


def session_question_trends(session: ReviewSession) -> dict:
    """Per-question series for session summary heatmap / answer-review grids."""
    answers = (
        session.answers.select_related("question", "selected_choice")
        .order_by("answered_at", "id")
    )
    seconds_per_question = session.seconds_per_question or 30
    confidence_points = []
    mistake_points = []
    review_points = []
    quick_count = 0
    quick_missed = 0
    unanswered_count = 0

    for index, answer in enumerate(answers, start=1):
        label = str(index)
        unanswered = answer_is_unanswered(answer)
        pace = pace_from_answer(answer, seconds_per_question)
        # Unanswered cells are always treated as incorrect in the review grid.
        is_correct = bool(answer.is_correct) and not unanswered
        if pace == PACE_QUICK:
            quick_count += 1
            if not is_correct:
                quick_missed += 1
        if unanswered:
            unanswered_count += 1

        confidence_points.append(
            {
                "label": label,
                "value": confidence_to_scale_0_3(answer.confidence),
                "answer_id": answer.pk,
            }
        )
        mistake_points.append(
            {
                "label": label,
                "value": 0 if is_correct else 1,
                "answer_id": answer.pk,
            }
        )
        review_points.append(
            {
                "label": label,
                "answer_id": answer.pk,
                "is_correct": is_correct,
                "unanswered": unanswered,
                "pace": pace,
                "pace_bars": PACE_BAR_COUNTS.get(pace, 0),
            }
        )

    return {
        "confidence": confidence_points,
        "mistakes": mistake_points,
        "review": review_points,
        "quick_count": quick_count,
        "quick_missed": quick_missed,
        "unanswered_count": unanswered_count,
    }


def topic_progress_summary(student: User) -> list[dict]:
    """Return per-topic accuracy stats for a student."""
    rows = (
        Answer.objects.filter(session__student=student)
        .values(
            "question__topic__name",
            "question__topic_id",
            "question__topic__subject_id",
        )
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
        .order_by("question__topic__name")
    )
    results = []
    for row in rows:
        total = row["total"]
        accuracy = round(row["correct"] / total * 100, 1) if total else 0.0
        results.append(
            {
                "topic_name": row["question__topic__name"],
                "topic_id": row["question__topic_id"],
                "subject_id": row["question__topic__subject_id"],
                "total": total,
                "correct": row["correct"],
                "accuracy": accuracy,
            }
        )
    return results


def enrolled_bsed_student_count() -> int:
    """Active BSED Math students (expected participation ceiling for overview charts)."""
    return User.objects.filter(
        role=User.Role.STUDENT,
        home_degree_program=User.HomeDegreeProgram.BSED_MATH,
        is_active=True,
    ).count()


def enrolled_bsed_students_by_year_level() -> list[dict]:
    """Active BSED Math students grouped by year level."""
    from django.db.models import Count

    from apps.questions.models import YearLevel

    # Counts keyed by year_level_id (None for students without a year level).
    raw = (
        User.objects.filter(
            role=User.Role.STUDENT,
            home_degree_program=User.HomeDegreeProgram.BSED_MATH,
            is_active=True,
        )
        .values("year_level_id")
        .annotate(count=Count("id"))
    )
    counts_by_id = {row["year_level_id"]: row["count"] for row in raw}

    rows: list[dict] = []
    for yl in YearLevel.objects.order_by("order"):
        rows.append(
            {
                "name": yl.name,
                "order": yl.order,
                "count": counts_by_id.get(yl.pk, 0),
            }
        )
    return rows


def professor_overview_summary(professor: User) -> dict:
    """Aggregate KPIs for the professor overview dashboard."""
    from django.db.models import Max
    from django.utils import timezone

    from apps.questions.models import Subject
    from apps.reviews.models import ExamSetup

    subject_count = Subject.objects.filter(
        program__slug=User.HomeDegreeProgram.BSED_MATH
    ).count()
    answers = Answer.objects.filter(
        session__course__professor=professor,
        session__course__program__slug=User.HomeDegreeProgram.BSED_MATH,
    )
    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    now = timezone.now()
    week_ago = now - timezone.timedelta(days=7)
    enabled_exam_setups = ExamSetup.objects.filter(
        course__professor=professor,
        course__is_archived=False,
        course__program__slug=User.HomeDegreeProgram.BSED_MATH,
        is_enabled=True,
    ).count()

    last_activity_at = (
        ReviewSession.objects.filter(
            course__professor=professor,
            course__program__slug=User.HomeDegreeProgram.BSED_MATH,
        )
        .aggregate(last=Max("started_at"))
        .get("last")
    )
    total_sessions = ReviewSession.objects.filter(
        course__professor=professor,
        course__program__slug=User.HomeDegreeProgram.BSED_MATH,
        status__in=[ReviewSession.Status.COMPLETED, ReviewSession.Status.EXPIRED],
    ).count()
    mistake_count = MistakeRecord.objects.filter(
        answer__session__course__professor=professor,
        answer__session__course__program__slug=User.HomeDegreeProgram.BSED_MATH,
    ).count()
    avg_mistakes_per_session = (
        round(mistake_count / total_sessions, 1) if total_sessions else 0.0
    )

    return {
        "course_count": subject_count,
        "subject_count": subject_count,
        "expected_students": enrolled_bsed_student_count(),
        "students_by_year_level": enrolled_bsed_students_by_year_level(),
        "student_count": ReviewSession.objects.filter(
            course__professor=professor,
            course__program__slug=User.HomeDegreeProgram.BSED_MATH,
        )
        .values("student")
        .distinct()
        .count(),
        "accuracy": accuracy,
        "sessions_this_week": ReviewSession.objects.filter(
            course__professor=professor,
            course__program__slug=User.HomeDegreeProgram.BSED_MATH,
            started_at__gte=week_ago,
        ).count(),
        "enabled_exam_setups": enabled_exam_setups,
        "total_sessions": total_sessions,
        "mistake_count": mistake_count,
        "avg_mistakes_per_session": avg_mistakes_per_session,
        "mistakes_subtext": f"{mistake_count} total",
        "as_of": now,
        "week_start": week_ago,
        "week_end": now,
        "last_activity_at": last_activity_at,
        "sessions_subtext": f"{total_sessions} total",
    }


def professor_overview_course_cards(professor: User) -> list[dict]:
    """Return per-course stats for the professor overview page."""
    from django.utils import timezone

    from apps.reviews.models import ExamSetup

    now = timezone.now()
    week_ago = now - timezone.timedelta(days=7)
    courses = Course.objects.filter(
        professor=professor,
        is_archived=False,
        program__slug=User.HomeDegreeProgram.BSED_MATH,
    ).select_related("program")

    cards = []
    for course in courses:
        student_ids = _course_student_ids(course)
        enrolled_count = student_ids.count()
        answers = _course_answers(course)
        total_answers = answers.count()
        correct_answers = answers.filter(is_correct=True).count()
        accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

        sessions_this_week = ReviewSession.objects.filter(
            course=course,
            started_at__gte=week_ago,
        ).count()

        exam_setup_enabled = ExamSetup.objects.filter(
            course=course,
            is_enabled=True,
        ).exists()

        last_session_at = (
            ReviewSession.objects.filter(course=course)
            .order_by("-started_at")
            .values_list("started_at", flat=True)
            .first()
        )

        cards.append(
            {
                "course": course,
                "enrolled_count": enrolled_count,
                "accuracy": accuracy,
                "sessions_this_week": sessions_this_week,
                "exam_setup_enabled": exam_setup_enabled,
                "last_session_at": last_session_at,
            }
        )
    return cards


def confidence_to_scale_0_3(value) -> int:
    """Map stored 1–5 / null confidence onto chart scale 0–3."""
    from apps.analytics.confidence import confidence_to_scale_0_3 as _map_confidence

    return _map_confidence(value)


def _confidence_scale_0_3_annotation():
    """ORM Case expression mapping Answer.confidence to 0–3 (null → 0)."""
    from django.db.models import Case, IntegerField, Value, When

    return Case(
        When(confidence__isnull=True, then=Value(0)),
        When(confidence__lte=2, then=Value(1)),
        When(confidence__lte=4, then=Value(2)),
        When(confidence__gte=5, then=Value(3)),
        default=Value(0),
        output_field=IntegerField(),
    )


def _confidence_share_point(label: str, answers) -> dict:
    """Build a stacked confidence share point for one session or bucket."""
    total = len(answers)
    if total == 0:
        return {
            "label": label,
            "value": 0.0,
            "sure": 0.0,
            "not_sure": 0.0,
            "guessing": 0.0,
            "none": 100.0,
            "correct_pct": 0.0,
        }

    sure = not_sure = guessing = none = correct = 0
    mapped_sum = 0
    for answer in answers:
        conf = getattr(answer, "confidence", None)
        mapped_sum += confidence_to_scale_0_3(conf)
        if conf is None:
            none += 1
        elif conf >= 5:
            sure += 1
        elif conf >= 3:
            not_sure += 1
        else:
            guessing += 1
        if getattr(answer, "is_correct", False):
            correct += 1

    def pct(count: int) -> float:
        return round(100.0 * count / total, 1)

    return {
        "label": label,
        "value": round(mapped_sum / total, 2),
        "sure": pct(sure),
        "not_sure": pct(not_sure),
        "guessing": pct(guessing),
        "none": pct(none),
        "correct_pct": round(100.0 * correct / total, 1),
    }


def build_confidence_insight(confidence_points: list[dict]) -> str:
    """Short callout comparing Sure share vs correct % across sessions/buckets."""
    rated = [
        p
        for p in confidence_points
        if (p.get("sure", 0) + p.get("not_sure", 0) + p.get("guessing", 0)) > 0
    ]
    if not rated:
        return (
            "Rate Guessing, Not sure, or Sure after each question to unlock "
            "confidence trends."
        )

    ahead = [
        p
        for p in rated
        if p.get("sure", 0) > (p.get("correct_pct", 0) + 8)
    ]
    latest = rated[-1]
    sure = latest.get("sure", 0)
    correct = latest.get("correct_pct", 0)
    if abs(sure - correct) <= 5:
        return (
            f"In your latest session they met: {sure:.0f}% Sure, "
            f"{correct:.0f}% correct."
        )
    if ahead:
        peak = max(ahead, key=lambda p: p.get("sure", 0) - p.get("correct_pct", 0))
        return (
            "Your confidence ran ahead of your results for several sessions. "
            f"Sure reached {peak.get('sure', 0):.0f}% while about "
            f"{peak.get('correct_pct', 0):.0f}% of your answers were correct. "
            f"In your latest session: {sure:.0f}% Sure, {correct:.0f}% correct."
        )
    if sure + 8 < correct:
        return (
            f"Your results ran ahead of your Sure ratings recently "
            f"({correct:.0f}% correct vs {sure:.0f}% Sure). "
            "Trust the work you are already doing."
        )
    return (
        f"Latest session: {sure:.0f}% Sure and {correct:.0f}% correct. "
        "Keep rating after each question to track calibration."
    )


def professor_overview_trends(professor: User) -> dict:
    """Bucketed trend series for the professor overview line chart.

    Returns all metrics × ranges so the client can switch without refetching.
    """
    from datetime import timedelta
    from django.utils import timezone

    now = timezone.now()
    course_filter = Q(course__professor=professor, course__is_archived=False)
    answer_filter = Q(
        session__course__professor=professor,
        session__course__is_archived=False,
    )

    ranges = {
        "weekly": {
            "trunc": TruncWeek,
            "count": 12,
            "delta": timedelta(weeks=1),
            "label": lambda d: d.strftime("%b %d"),
            "key": lambda d: d.date().isoformat() if hasattr(d, "date") else str(d),
        },
        "monthly": {
            "trunc": TruncMonth,
            "count": 12,
            "delta": timedelta(days=31),
            "label": lambda d: d.strftime("%b %Y"),
            "key": lambda d: d.strftime("%Y-%m"),
        },
        "yearly": {
            "trunc": TruncYear,
            "count": 5,
            "delta": timedelta(days=366),
            "label": lambda d: d.strftime("%Y"),
            "key": lambda d: d.strftime("%Y"),
        },
    }

    def _bucket_starts(cfg):
        starts = []
        if cfg["trunc"] is TruncWeek:
            d = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            for i in range(cfg["count"] - 1, -1, -1):
                starts.append(d - timedelta(weeks=i))
        elif cfg["trunc"] is TruncMonth:
            y, m = now.year, now.month
            for i in range(cfg["count"] - 1, -1, -1):
                mm = m - i
                yy = y
                while mm <= 0:
                    mm += 12
                    yy -= 1
                starts.append(
                    now.replace(
                        year=yy,
                        month=mm,
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                )
        else:
            for i in range(cfg["count"] - 1, -1, -1):
                starts.append(
                    now.replace(
                        year=now.year - i,
                        month=1,
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                )
        return starts

    def _fill(series_map, cfg):
        points = []
        for start in _bucket_starts(cfg):
            k = cfg["key"](start)
            points.append(
                {
                    "label": cfg["label"](start),
                    "value": series_map.get(k, 0),
                }
            )
        return points

    def _fill_confidence(conf_map, cfg):
        points = []
        for start in _bucket_starts(cfg):
            k = cfg["key"](start)
            bucket = conf_map.get(k)
            if bucket:
                points.append(dict(bucket, label=cfg["label"](start)))
            else:
                point = _confidence_share_point(cfg["label"](start), [])
                point["student_count"] = 0
                points.append(point)
        return points

    def _fill_scores(scores_map, cfg):
        points = []
        for start in _bucket_starts(cfg):
            k = cfg["key"](start)
            bucket = scores_map.get(k, {})
            points.append(
                {
                    "label": cfg["label"](start),
                    "value": bucket.get("value", 0),
                    "student_count": bucket.get("student_count", 0),
                }
            )
        return points

    result = {}
    for range_key, cfg in ranges.items():
        trunc_fn = cfg["trunc"]
        earliest = _bucket_starts(cfg)[0]

        session_rows = (
            ReviewSession.objects.filter(course_filter, started_at__gte=earliest)
            .annotate(bucket=trunc_fn("started_at"))
            .values("bucket")
            .annotate(value=Count("student_id", distinct=True))
            .order_by("bucket")
        )
        students_map = {
            cfg["key"](row["bucket"]): row["value"]
            for row in session_rows
            if row["bucket"]
        }

        from django.db.models import IntegerField, OuterRef, Subquery

        correct_count_subq = (
            Answer.objects.filter(session_id=OuterRef("pk"), is_correct=True)
            .values("session_id")
            .annotate(c=Count("id"))
            .values("c")[:1]
        )
        score_rows = (
            ReviewSession.objects.filter(
                course_filter,
                status=ReviewSession.Status.COMPLETED,
                started_at__gte=earliest,
            )
            .annotate(
                bucket=trunc_fn("started_at"),
                score=Subquery(correct_count_subq, output_field=IntegerField()),
            )
            .values("bucket")
            .annotate(
                value=Avg("score"),
                student_count=Count("student_id", distinct=True),
            )
            .order_by("bucket")
        )
        scores_map = {}
        for row in score_rows:
            if not row["bucket"]:
                continue
            k = cfg["key"](row["bucket"])
            scores_map[k] = {
                "value": round(float(row["value"] or 0), 1),
                "student_count": row["student_count"] or 0,
            }

        conf_rows = (
            Answer.objects.filter(
                answer_filter,
                answered_at__gte=earliest,
            )
            .annotate(bucket=trunc_fn("answered_at"))
            .values_list("bucket", "confidence", "is_correct")
        )
        answers_by_bucket: dict[str, list] = {}
        for bucket, confidence, is_correct in conf_rows:
            if not bucket:
                continue
            k = cfg["key"](bucket)
            answers_by_bucket.setdefault(k, []).append(
                type(
                    "Row",
                    (),
                    {"confidence": confidence, "is_correct": is_correct},
                )()
            )

        student_rows = (
            Answer.objects.filter(
                answer_filter,
                answered_at__gte=earliest,
            )
            .annotate(bucket=trunc_fn("answered_at"))
            .values("bucket")
            .annotate(student_count=Count("session__student_id", distinct=True))
        )
        student_count_map = {
            cfg["key"](row["bucket"]): row["student_count"] or 0
            for row in student_rows
            if row["bucket"]
        }

        confidence_map = {}
        for k, bucket_answers in answers_by_bucket.items():
            point = _confidence_share_point(k, bucket_answers)
            point["student_count"] = student_count_map.get(k, 0)
            confidence_map[k] = point

        confidence_points = _fill_confidence(confidence_map, cfg)
        result[range_key] = {
            "students": _fill(students_map, cfg),
            "scores": _fill_scores(scores_map, cfg),
            "confidence": confidence_points,
            "confidence_insight": build_confidence_insight(confidence_points),
        }

    return result


def _course_student_ids(course: Course):
    """Students who have practiced via this course offering."""
    return (
        ReviewSession.objects.filter(course=course)
        .values_list("student_id", flat=True)
        .distinct()
    )


def _course_answers(course: Course, student: User | None = None):
    qs = Answer.objects.filter(session__course=course)
    if student:
        qs = qs.filter(session__student=student)
    return qs


def _peer_accuracy_for_answers(answers_qs) -> float:
    """Lightweight class/section average accuracy from an answers queryset."""
    total = answers_qs.count()
    if not total:
        return 0.0
    correct = answers_qs.filter(is_correct=True).count()
    return round(correct / total * 100, 1)


def course_performance_summary(course: Course) -> dict:
    """Return aggregated performance for a course offering."""
    student_ids = _course_student_ids(course)

    sessions = ReviewSession.objects.filter(
        course=course,
        student_id__in=student_ids,
        status=ReviewSession.Status.COMPLETED,
    )
    answers = _course_answers(course)

    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    confidence_by_topic = list(
        answers.values("question__topic__name")
        .annotate(
            avg_confidence=Avg(_confidence_scale_0_3_annotation()),
            total=Count("id"),
        )
        .order_by("question__topic__name")
    )
    for row in confidence_by_topic:
        row["avg_confidence"] = round(float(row["avg_confidence"] or 0), 1)

    mistake_patterns = list(
        MistakeRecord.objects.filter(
            student_id__in=student_ids,
            question__topic__subject__program=course.program,
        )
        .values("topic__name")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:10]
    )

    mistake_patterns_by_error_type = list(
        MistakeRecord.objects.filter(student_id__in=student_ids, error_type__isnull=False)
        .values("error_type__label", "error_type__slug")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:10]
    )

    participant_count = student_ids.count()
    active_sessions = ReviewSession.objects.filter(
        course=course,
        status=ReviewSession.Status.ACTIVE,
    ).count()

    feedback_views = FeedbackView.objects.filter(
        answer__session__course=course,
    ).count()

    calibration_matrix = confidence_tier_matrix(answers)
    misconception_topic_list = misconception_topics(answers)

    return {
        "course": course,
        "enrolled_count": participant_count,
        "sessions_completed": sessions.count(),
        "active_sessions": active_sessions,
        "accuracy": accuracy,
        "total_answers": total_answers,
        "confidence_by_topic": confidence_by_topic,
        "mistake_patterns": mistake_patterns,
        "mistake_patterns_by_error_type": mistake_patterns_by_error_type,
        "feedback_views": feedback_views,
        "calibration_matrix": calibration_matrix,
        "misconception_topics": misconception_topic_list,
    }


def program_performance_summary(program: Program, department=None) -> dict:
    """Return program-level analytics, optionally scoped to a department's students."""
    if department:
        student_ids = students_in_department(department).values_list("pk", flat=True)
        sessions = ReviewSession.objects.filter(
            student_id__in=student_ids,
            topic__subject__program=program,
            status=ReviewSession.Status.COMPLETED,
        )
        answers = Answer.objects.filter(
            session__student_id__in=student_ids,
            question__topic__subject__program=program,
        )
    else:
        sessions = ReviewSession.objects.filter(
            topic__subject__program=program,
            status=ReviewSession.Status.COMPLETED,
        )
        answers = Answer.objects.filter(question__topic__subject__program=program)

    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    question_distribution = list(
        Question.objects.filter(topic__subject__program=program, status=Question.Status.APPROVED, is_active=True)
        .values("topic__name", "difficulty")
        .annotate(count=Count("id"))
        .order_by("topic__name", "difficulty")
    )

    recurring_mistakes = list(
        MistakeRecord.objects.filter(topic__subject__program=program)
        .values("topic__name")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:10]
    )

    topic_count = Topic.objects.filter(subject__program=program).count()

    return {
        "program": program,
        "topic_count": topic_count,
        "sessions_completed": sessions.count(),
        "accuracy": accuracy,
        "total_answers": total_answers,
        "question_distribution": question_distribution,
        "recurring_mistakes": recurring_mistakes,
    }


def department_math_analytics(department) -> dict:
    """Cross-program analytics for students in a chairperson's department."""
    programs = home_programs_for_department(department)
    breakdown = []

    for program_value in programs:
        label = dict(User.HomeDegreeProgram.choices).get(program_value, program_value)
        students = User.objects.filter(role=User.Role.STUDENT, home_degree_program=program_value)
        student_ids = students.values_list("pk", flat=True)
        answers = Answer.objects.filter(session__student_id__in=student_ids)
        total = answers.count()
        correct = answers.filter(is_correct=True).count()
        accuracy = round(correct / total * 100, 1) if total else 0.0
        breakdown.append(
            {
                "program": program_value,
                "label": label,
                "student_count": students.count(),
                "accuracy": accuracy,
                "total_answers": total,
            }
        )

    student_ids = students_in_department(department).values_list("pk", flat=True)
    answers = Answer.objects.filter(session__student_id__in=student_ids)
    total = answers.count()
    correct = answers.filter(is_correct=True).count()

    return {
        "department": department,
        "breakdown": breakdown,
        "overall_accuracy": round(correct / total * 100, 1) if total else 0.0,
        "total_answers": total,
    }


def get_student_mistake_patterns(student: User) -> list[dict]:
    """Return mistake counts grouped by topic for a student."""
    return list(
        MistakeRecord.objects.filter(student=student)
        .values("topic__name", "topic_id")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")
    )


def get_student_topic_answers(student: User, topic_id: int):
    """Return topic and answers for a student's activity on that topic."""
    from apps.questions.models import Topic
    from apps.reviews.models import Answer

    answers = (
        Answer.objects.filter(
            session__student=student,
            question__topic_id=topic_id,
        )
        .select_related(
            "question",
            "selected_choice",
            "session",
            "mistake_record",
            "mistake_record__error_type",
        )
        .prefetch_related("question__choices", "question__explanation_steps")
        .order_by("-answered_at")
    )
    if not answers.exists():
        return None, Answer.objects.none()

    topic = Topic.objects.filter(pk=topic_id).first()
    return topic, answers


def _confidence_label_short(avg_confidence: float | None) -> str:
    """Map average answer confidence to a short display label."""
    if avg_confidence is None:
        return "—"
    rounded = round(avg_confidence)
    if rounded <= 2:
        return "Guessing"
    if rounded <= 4:
        return "Not sure"
    return "Sure"


def _session_review_status_label(accuracy: float) -> str:
    if accuracy < 70:
        return "Needs review"
    return "Complete"


def annotate_session_metrics(queryset):
    """Annotate sessions with answer counts and average confidence."""
    return queryset.annotate(
        session_avg_confidence=Avg("answers__confidence"),
        session_answer_count=Count("answers"),
        session_correct_count=Count("answers", filter=Q(answers__is_correct=True)),
    )


def build_session_history_rows(sessions) -> list[dict]:
    """Build display rows for session history tables."""
    from apps.analytics.confidence import confidence_tier_key

    rows = []
    for session in sessions:
        total = getattr(session, "session_answer_count", None)
        if total is None:
            total = session.total_questions
        correct = getattr(session, "session_correct_count", None)
        if correct is None:
            correct = session.correct_count
        accuracy = round(correct / total * 100, 1) if total else 0.0
        avg_conf = getattr(session, "session_avg_confidence", None)
        if avg_conf is None and total:
            avg_conf = session.answers.aggregate(avg=Avg("confidence"))["avg"]
        if avg_conf is not None:
            avg_conf = round(float(avg_conf), 1)

        segments = {"none": 0, "low": 0, "average": 0, "high": 0}
        duration_seconds = 0
        subject_name = ""
        subject_code = ""
        subject_ids: set[int] = set()
        if total:
            prefetched = getattr(session, "_prefetched_objects_cache", {}).get("answers")
            if prefetched is not None:
                answer_rows = prefetched
            else:
                answer_rows = session.answers.select_related("question__topic__subject")
            for answer in answer_rows:
                segments[confidence_tier_key(answer.confidence)] += 1
                duration_seconds += answer.time_spent_seconds or 0
                topic = getattr(answer.question, "topic", None)
                if topic and getattr(topic, "subject_id", None):
                    subject_ids.add(topic.subject_id)
                    if not subject_code:
                        subj = topic.subject
                        subject_name = subj.name
                        subject_code = subj.code
        if not subject_code and getattr(session, "topic_id", None):
            subj = session.topic.subject
            subject_name = subj.name
            subject_code = subj.code
            subject_ids.add(subj.pk)

        # Include M2M subjects selected for the session when present.
        m2m_cache = getattr(session, "_prefetched_objects_cache", {}).get("subjects")
        if m2m_cache is not None:
            for subj in m2m_cache:
                subject_ids.add(subj.pk)
        elif hasattr(session, "subjects"):
            for sid in session.subjects.values_list("pk", flat=True):
                subject_ids.add(sid)

        subjects_taken_count = len(subject_ids)

        duration_min = (
            max(1, round(duration_seconds / 60))
            if duration_seconds
            else (session.duration_minutes or 0)
        )
        seg_total = sum(segments.values()) or 1
        segment_pcts = {
            k: round(v / seg_total * 100, 1) for k, v in segments.items()
        }

        rows.append(
            {
                "session": session,
                "date": session.started_at,
                "topic_name": session.topic.name if session.topic_id else "—",
                "subject_name": subject_name,
                "subject_code": subject_code,
                "subjects_taken_count": subjects_taken_count,
                "subjects_taken_display": (
                    str(subjects_taken_count) if subjects_taken_count else "—"
                ),
                "avg_confidence": avg_conf,
                "confidence_label": _confidence_label_short(avg_conf),
                "confidence_segments": segments,
                "confidence_segment_pcts": segment_pcts,
                "correct_count": correct,
                "total_questions": total,
                "accuracy": accuracy,
                "score_display": f"{correct}/{total}" if total else "—",
                "status_label": _session_review_status_label(accuracy),
                "duration_minutes": duration_min,
                "summary_url": None,
            }
        )
    return rows


def build_confidence_performance_series(sessions) -> list[dict]:
    """Per-session data for confidence (0–3) vs performance (%) bar chart."""
    series = []
    for session in sessions:
        total = getattr(session, "session_answer_count", None)
        if total is None:
            total = session.total_questions
        correct = getattr(session, "session_correct_count", None)
        if correct is None:
            correct = session.correct_count
        accuracy = round(correct / total * 100, 1) if total else 0.0
        session_answers = list(session.answers.all())
        if session_answers:
            mapped = [confidence_to_scale_0_3(a.confidence) for a in session_answers]
            avg_conf = round(sum(mapped) / len(mapped), 2)
        else:
            avg_conf = 0.0
        started = session.started_at
        label = f"{session.topic.name} {started.strftime('%m-%d %I:%M %p')}" if started else session.topic.name
        series.append(
            {
                "label": label,
                "topic": session.topic.name,
                "confidence": avg_conf,
                "performance": accuracy,
            }
        )
    return series


def get_roster_summaries(course: Course) -> list[dict]:
    """Return per-student summary rows from session participation."""
    student_ids = list(_course_student_ids(course))
    students = User.objects.filter(pk__in=student_ids).order_by("last_name", "email")
    answers = Answer.objects.filter(session__course=course)

    roster = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        total = student_answers.count()
        correct = student_answers.filter(is_correct=True).count()
        accuracy = round(correct / total * 100, 1) if total else 0.0
        avg_conf = student_answers.aggregate(avg=Avg("confidence"))["avg"] or 0
        total_seconds = student_answers.aggregate(total=Sum("time_spent_seconds"))["total"] or 0
        sessions_count = ReviewSession.objects.filter(
            student=student,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        ).count()
        roster.append(
            {
                "student": student,
                "sessions_completed": sessions_count,
                "accuracy": accuracy,
                "avg_confidence": round(avg_conf, 1),
                "review_hours": round(total_seconds / 3600, 1),
            }
        )
    return roster


def get_professor_students_with_exams(
    professor: User, *, include_archived: bool = False
) -> list[dict]:
    """Students in faculty-assigned sections who completed exams on assigned subjects.

    Option B: no profile sections/subjects → empty roster.
    """
    from apps.users.assignment_services import (
        faculty_has_chat_scope,
        get_faculty_profile_section_ids,
        get_faculty_profile_subject_ids,
    )

    if not faculty_has_chat_scope(professor):
        return []

    section_ids = get_faculty_profile_section_ids(professor)
    subject_ids = get_faculty_profile_subject_ids(professor)
    completed = (
        ReviewSession.objects.filter(
            student__section_id__in=section_ids,
            status=ReviewSession.Status.COMPLETED,
        )
        .filter(
            Q(subjects__in=subject_ids)
            | Q(topic__subject_id__in=subject_ids)
            | Q(course__code__in=Subject.objects.filter(pk__in=subject_ids).values("code"))
        )
        .select_related("student", "student__section", "course")
        .distinct()
        .order_by("-ended_at", "-started_at")
    )
    if not include_archived:
        completed = completed.filter(student__is_archived=False)

    by_student: dict[int, dict] = {}
    for session in completed:
        student = session.student
        if student is None:
            continue
        if student.pk not in by_student:
            by_student[student.pk] = {
                "student": student,
                "sessions_completed": 0,
                "last_activity": session.ended_at or session.started_at,
                "primary_course": session.course,
            }
        by_student[student.pk]["sessions_completed"] += 1
        activity = session.ended_at or session.started_at
        if activity and (
            by_student[student.pk]["last_activity"] is None
            or activity > by_student[student.pk]["last_activity"]
        ):
            by_student[student.pk]["last_activity"] = activity

    # Distinct assigned subjects answered by these students.
    subject_counts = {
        row["session__student_id"]: row["n"]
        for row in Answer.objects.filter(
            session__student_id__in=by_student.keys(),
            question__topic__subject_id__in=subject_ids,
        )
        .values("session__student_id")
        .annotate(n=Count("question__topic__subject_id", distinct=True))
    }

    from apps.analytics.models import MistakeRecord

    mistake_counts = {
        row["student_id"]: row["n"]
        for row in MistakeRecord.objects.filter(
            student_id__in=by_student.keys(),
            question__topic__subject_id__in=subject_ids,
        )
        .values("student_id")
        .annotate(n=Count("id"))
    }

    rows = list(by_student.values())
    for row in rows:
        row["subjects_taken_count"] = subject_counts.get(row["student"].pk, 0)
        row["courses_label"] = str(row["subjects_taken_count"])
        row["mistake_count"] = mistake_counts.get(row["student"].pk, 0)
    rows.sort(
        key=lambda r: (
            (r["student"].last_name or "").lower(),
            (r["student"].email or "").lower(),
        )
    )
    return rows


def student_professor_summary(student: User, professor: User) -> dict:
    """Performance summary for a student across a professor's visible scope.

    Includes sessions on courses they own plus completed exams in their
    assigned section/subject profile scope (same gate as the Students list).
    """
    from apps.users.assignment_services import (
        faculty_has_chat_scope,
        get_faculty_profile_section_ids,
        get_faculty_profile_subject_ids,
    )

    owned = Q(course__professor=professor)
    scoped = Q(pk__in=[])
    if faculty_has_chat_scope(professor):
        section_ids = get_faculty_profile_section_ids(professor)
        subject_ids = get_faculty_profile_subject_ids(professor)
        if student.section_id in section_ids:
            scoped = Q(subjects__in=subject_ids) | Q(
                topic__subject_id__in=subject_ids
            ) | Q(
                course__code__in=Subject.objects.filter(pk__in=subject_ids).values(
                    "code"
                )
            )

    sessions = (
        ReviewSession.objects.filter(
            student=student,
            status=ReviewSession.Status.COMPLETED,
        )
        .filter(owned | scoped)
        .select_related("topic", "topic__subject", "course")
        .distinct()
    )
    session_ids = sessions.values_list("pk", flat=True)
    answers = Answer.objects.filter(session_id__in=session_ids)
    return _build_student_activity_summary(
        student,
        sessions,
        answers,
        weak_topics_filter=Q(answer__session_id__in=session_ids),
        confidence_group_by="subject",
    )


def get_topic_mastery_heatmap(course: Course) -> dict:
    """Build question×confidence-tier heatmap for a course offering.

    Catalog offerings use subject-wide answers (any year) instead of session.course.
    """
    from apps.questions.models import Subject

    subject = Subject.objects.filter(code=course.code, program=course.program).first()
    if (course.section or "").strip() == "Catalog" and subject:
        return get_subject_heatmap(subject)
    return _heatmap_from_answers(
        _course_answers(course).select_related("question__topic"),
        student_ids=_course_student_ids(course),
        subject=subject,
    )


def section_heatmap_subjects(section):
    """Subjects with answer data from students in this ProgramSection."""
    from apps.questions.models import Subject

    return (
        Subject.objects.filter(
            topics__questions__answers__session__student__section=section,
        )
        .distinct()
        .order_by("code", "name")
    )


def get_section_heatmap(section, subject=None) -> dict:
    """Heatmap for answers from students in a ProgramSection.

    When ``subject`` is set, only that curriculum subject's questions are
    included (one subject at a time on the section heatmap).
    """
    answers = Answer.objects.filter(
        session__student__section=section
    ).select_related("question__topic", "session__student")
    if subject is not None:
        answers = answers.filter(question__topic__subject=subject)
    student_ids = answers.values_list("session__student_id", flat=True).distinct()
    return _heatmap_from_answers(answers, student_ids=student_ids, subject=subject)


def get_subject_heatmap(subject) -> dict:
    """Heatmap for all answers tied to a curriculum subject (any year)."""
    answers = Answer.objects.filter(
        question__topic__subject=subject
    ).select_related("question__topic", "session__student")
    student_ids = answers.values_list("session__student_id", flat=True).distinct()
    return _heatmap_from_answers(answers, student_ids=student_ids, subject=subject)


def _heatmap_from_answers(answers, student_ids, *, subject=None) -> dict:
    from apps.analytics.confidence import CONFIDENCE_TIER_LABELS, confidence_tier_key

    question_map: dict[int, dict] = {}
    for answer in answers:
        question = answer.question
        if question.id not in question_map:
            stem = (question.stem or "").strip()
            if len(stem) > 80:
                stem = stem[:77] + "..."
            question_map[question.id] = {
                "question_id": question.id,
                "question_stem": stem,
                "topic_name": question.topic.name,
                "none": 0,
                "low": 0,
                "average": 0,
                "high": 0,
                "mistakes": 0,
                "total": 0,
            }
        tier = confidence_tier_key(answer.confidence)
        question_map[question.id][tier] += 1
        question_map[question.id]["total"] += 1
        if not answer.is_correct:
            question_map[question.id]["mistakes"] += 1

    # Q1…Qn among questions in this heatmap (creation order), not DB pk.
    ordered_ids = sorted(question_map.keys())
    label_by_id: dict[int, tuple[int, str]] = {
        qid: (index, f"Q{index}") for index, qid in enumerate(ordered_ids, start=1)
    }

    for qid, row in question_map.items():
        number, label = label_by_id[qid]
        row["q_number"] = number
        row["q_label"] = label

    # Table / chart order: Q1 → Qn
    questions = sorted(question_map.values(), key=lambda q: q["q_number"])
    callouts = {
        "low_confidence": [q for q in questions if (q["none"] + q["low"]) >= 2],
    }

    students = User.objects.filter(pk__in=list(student_ids))
    rows = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        counts = {"none": 0, "low": 0, "average": 0, "high": 0}
        for answer in student_answers:
            counts[confidence_tier_key(answer.confidence)] += 1
        dominant = max(counts, key=counts.get) if student_answers.exists() else "none"
        rows.append(
            {
                "student_id": student.pk,
                "student_name": student.get_full_name() or student.email,
                "counts": counts,
                "dominant": dominant,
                "total": student_answers.count(),
            }
        )

    return {
        "questions": questions,
        "topics": questions,
        "student_rows": sorted(rows, key=lambda r: r["student_name"]),
        "tier_labels": CONFIDENCE_TIER_LABELS,
        "callouts": callouts,
        "matrix": confidence_tier_matrix(answers),
    }


def _build_student_heatmap_rows(course: Course, answers) -> list[dict]:
    """Per-student dominant confidence tier."""
    from apps.analytics.confidence import confidence_tier_key

    student_ids = _course_student_ids(course)
    students = User.objects.filter(pk__in=student_ids)
    rows = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        counts = {"none": 0, "low": 0, "average": 0, "high": 0}
        for answer in student_answers:
            counts[confidence_tier_key(answer.confidence)] += 1
        dominant = max(counts, key=counts.get) if student_answers.exists() else "none"
        rows.append(
            {
                "student_id": student.pk,
                "student_name": student.get_full_name() or student.email,
                "counts": counts,
                "dominant": dominant,
                "total": student_answers.count(),
            }
        )
    return sorted(rows, key=lambda r: r["student_name"])


def get_step_feedback_stats(question: Question) -> list[dict]:
    """Return per-step view counts for a question's explanation."""
    from apps.reviews.models import StepFeedbackView

    stats = []
    for step in question.explanation_steps.all():
        stats.append(
            {
                "step": step,
                "view_count": StepFeedbackView.objects.filter(explanation_step=step).count(),
            }
        )
    return stats


def get_intervention_list(course: Course) -> list[dict]:
    """Return students flagged for professor intervention in a course."""
    from django.utils import timezone

    from apps.analytics.confidence import (
        CLASSIFICATION_LUCKY_GUESS,
        CLASSIFICATION_MISCONCEPTION,
        classify_answer,
    )

    student_ids = list(_course_student_ids(course))
    students = User.objects.filter(pk__in=student_ids).order_by("last_name", "email")
    answers = _course_answers(course)
    now = timezone.now()
    cutoff = now - timezone.timedelta(days=14)

    rows = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        total = student_answers.count()
        correct = student_answers.filter(is_correct=True).count()
        accuracy = round(correct / total * 100, 1) if total else 0.0
        avg_confidence = student_answers.aggregate(
            avg=Avg(_confidence_scale_0_3_annotation())
        )["avg"] or 0
        sessions_count = ReviewSession.objects.filter(
            student=student,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        ).count()
        recent_sessions = ReviewSession.objects.filter(
            student=student,
            course=course,
            started_at__gte=cutoff,
        ).count()

        misconception_count = 0
        lucky_guess_count = 0
        for answer in student_answers.values("confidence", "is_correct"):
            classification = classify_answer(answer["confidence"], answer["is_correct"])
            if classification == CLASSIFICATION_MISCONCEPTION:
                misconception_count += 1
            elif classification == CLASSIFICATION_LUCKY_GUESS:
                lucky_guess_count += 1

        flags = []
        if misconception_count >= 2:
            flags.append("overconfident")
        if recent_sessions == 0 and student_ids:
            flags.append("under_practicing")
        if lucky_guess_count >= 2:
            flags.append("lucky_guess_pattern")
        if total >= 5 and accuracy < 60:
            flags.append("low_accuracy")

        if not flags:
            continue

        dominant_issue = flags[0]
        action_map = {
            "overconfident": "Schedule calibration discussion; assign targeted misconception review",
            "under_practicing": "Encourage review sessions; check review window access",
            "lucky_guess_pattern": "Assign confidence-building practice on weak topics",
            "low_accuracy": "Recommend remedial review on lowest-accuracy topics",
        }
        suggested_action = action_map.get(dominant_issue, "Follow up with student")

        rows.append(
            {
                "student": student,
                "flags": flags,
                "dominant_issue": dominant_issue.replace("_", " ").title(),
                "suggested_action": suggested_action,
                "accuracy": accuracy,
                "avg_confidence": round(avg_confidence, 1),
                "sessions": sessions_count,
                "misconception_count": misconception_count,
                "lucky_guess_count": lucky_guess_count,
            }
        )

    priority = {"overconfident": 0, "low_accuracy": 1, "under_practicing": 2, "lucky_guess_pattern": 3}
    rows.sort(key=lambda r: (priority.get(r["flags"][0], 9), -r["misconception_count"]))
    return rows


def _section_answers(section, student: User | None = None):
    """Answers from students enrolled in a ProgramSection (any subject)."""
    qs = Answer.objects.filter(session__student__section=section)
    if student:
        qs = qs.filter(session__student=student)
    return qs


def _section_student_ids(section):
    return (
        ReviewSession.objects.filter(student__section=section)
        .values_list("student_id", flat=True)
        .distinct()
    )


def section_performance_summary(section) -> dict:
    """Aggregate analytics for students in a ProgramSection across all subjects."""
    student_ids = _section_student_ids(section)
    sessions = ReviewSession.objects.filter(
        student__section=section,
        status=ReviewSession.Status.COMPLETED,
    )
    answers = _section_answers(section)

    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    subject_breakdown = list(
        answers.values(
            "question__topic__subject__code",
            "question__topic__subject__name",
            "question__topic__subject_id",
        )
        .annotate(
            answer_count=Count("id"),
            correct_count=Count("id", filter=Q(is_correct=True)),
            student_count=Count("session__student_id", distinct=True),
        )
        .order_by("question__topic__subject__code")
    )
    for row in subject_breakdown:
        total = row["answer_count"]
        row["accuracy"] = round(row["correct_count"] / total * 100, 1) if total else 0.0
        row["code"] = row["question__topic__subject__code"]
        row["name"] = row["question__topic__subject__name"]
        row["subject_id"] = row["question__topic__subject_id"]

    calibration_matrix = confidence_tier_matrix(answers)
    misconception_topic_list = misconception_topics(answers)

    return {
        "section": section,
        "enrolled_count": student_ids.count(),
        "sessions_completed": sessions.count(),
        "accuracy": accuracy,
        "total_answers": total_answers,
        "subject_breakdown": subject_breakdown,
        "calibration_matrix": calibration_matrix,
        "misconception_topics": misconception_topic_list,
    }


def get_section_roster_summaries(
    section, *, include_archived: bool = False
) -> list[dict]:
    """Per-student rows for every student enrolled in a ProgramSection."""
    students = User.objects.filter(section=section, role=User.Role.STUDENT)
    if not include_archived:
        students = students.filter(is_archived=False)
    students = students.select_related("year_level", "section").order_by(
        "last_name", "email"
    )
    answers = _section_answers(section)
    roster = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        total = student_answers.count()
        correct = student_answers.filter(is_correct=True).count()
        accuracy = round(correct / total * 100, 1) if total else 0.0
        avg_conf = student_answers.aggregate(avg=Avg("confidence"))["avg"] or 0
        sessions_count = ReviewSession.objects.filter(
            student=student,
            student__section=section,
            status=ReviewSession.Status.COMPLETED,
        ).count()
        subject_codes = {
            code
            for code in student_answers.values_list(
                "question__topic__subject__code", flat=True
            )
            if code
        }
        if not subject_codes:
            subject_codes.update(
                code
                for code in ReviewSession.objects.filter(
                    student=student,
                    status=ReviewSession.Status.COMPLETED,
                )
                .filter(student__section=section)
                .values_list("subjects__code", flat=True)
                if code
            )
        subjects_taken = sorted(subject_codes)
        roster.append(
            {
                "student": student,
                "sessions_completed": sessions_count,
                "questions_answered": total,
                "accuracy": accuracy,
                "avg_confidence": round(avg_conf, 1),
                "subjects_taken": subjects_taken,
                "subjects_taken_count": len(subjects_taken),
                "year_level": student.year_level.name if student.year_level_id else "",
            }
        )
    return roster


def _build_confidence_stack_rows(answers, *, group_by: str = "topic") -> list[dict]:
    """Stacked confidence rows for student detail (topic or subject)."""
    if group_by == "subject":
        name_field = "question__topic__subject__name"
        code_field = "question__topic__subject__code"
    else:
        name_field = "question__topic__name"
        code_field = "question__topic__subject__code"

    rows = list(
        answers.values(name_field, code_field)
        .annotate(
            total=Count("id"),
            none=Count("id", filter=Q(confidence__isnull=True)),
            low=Count("id", filter=Q(confidence=1)),
            average=Count("id", filter=Q(confidence=3)),
            high=Count("id", filter=Q(confidence=5)),
        )
        .order_by(name_field)
    )
    result = []
    for row in rows:
        total = row["total"] or 1
        avg_high = row["average"] + row["high"]
        avg_high_pct = round(avg_high / total * 100, 1)
        name = row[name_field] or "—"
        result.append(
            {
                "name": name,
                "code": row[code_field] or "",
                "none": row["none"],
                "low": row["low"],
                "average": row["average"],
                "high": row["high"],
                "total": row["total"],
                "avg_high_pct": avg_high_pct,
                "none_pct": round(row["none"] / total * 100, 1),
                "low_pct": round(row["low"] / total * 100, 1),
                "average_pct": round(row["average"] / total * 100, 1),
                "high_pct": round(row["high"] / total * 100, 1),
            }
        )
    # Lowest avg/high first for triage (like heatmap priority)
    result.sort(key=lambda r: (r["avg_high_pct"], -r["total"]))
    return result


def _build_student_activity_summary(
    student: User,
    sessions,
    answers,
    *,
    weak_topics_filter: Q | None = None,
    confidence_group_by: str = "topic",
) -> dict:
    """Shared KPI/chart payload for course, subject, or section student detail."""
    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0
    avg_confidence = answers.aggregate(avg=Avg("confidence"))["avg"] or 0
    total_seconds = answers.aggregate(total=Sum("time_spent_seconds"))["total"] or 0
    review_hours = round(total_seconds / 3600, 1)

    accuracy_trend = list(
        sessions.annotate(date=TruncDate("started_at"))
        .values("date")
        .annotate(
            total=Count("answers"),
            correct=Count("answers", filter=Q(answers__is_correct=True)),
        )
        .order_by("date")
    )
    for item in accuracy_trend:
        total = item["total"]
        item["accuracy"] = round(item["correct"] / total * 100, 1) if total else 0

    mistake_qs = MistakeRecord.objects.filter(student=student)
    if weak_topics_filter is not None:
        mistake_qs = mistake_qs.filter(weak_topics_filter)
    weak_topics = list(
        mistake_qs.values("topic__name")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:5]
    )

    ordered_sessions = annotate_session_metrics(
        sessions.select_related("topic", "topic__subject")
        .prefetch_related(
            Prefetch(
                "answers",
                queryset=Answer.objects.select_related("question__topic__subject"),
            )
        )
        .order_by("-started_at")[:8]
    )
    session_list = list(ordered_sessions)
    last_session = session_list[0] if session_list else None
    matrix = confidence_tier_matrix(answers)

    high_avg_count = answers.filter(confidence__in=[3, 5]).count()
    high_avg_rate = (
        round(high_avg_count / total_answers * 100, 1) if total_answers else 0.0
    )

    subjects_taken = sorted(
        {
            code
            for code in answers.values_list(
                "question__topic__subject__code", flat=True
            )
            if code
        }
    )

    confidence_stacks = _build_confidence_stack_rows(
        answers, group_by=confidence_group_by
    )
    follow_ups = [
        {
            "name": row["name"],
            "detail": (
                f"{row['avg_high_pct']}% Average/High confidence across "
                f"{row['total']} answer{'s' if row['total'] != 1 else ''}."
            ),
            "kind": "weak",
        }
        for row in confidence_stacks
        if row["avg_high_pct"] < 50
    ][:5]

    session_ids = [s.pk for s in session_list]
    mistake_counts_by_session = {}
    if session_ids:
        for row in (
            MistakeRecord.objects.filter(
                answer__session_id__in=session_ids, student=student
            )
            .values("answer__session_id")
            .annotate(mistake_count=Count("id"))
        ):
            mistake_counts_by_session[row["answer__session_id"]] = row["mistake_count"]

    from django.utils import timezone

    dashboard_trends = {"confidence": [], "mistakes": [], "confidence_insight": ""}
    for index, session in enumerate(reversed(session_list), start=1):
        ordinal = _ordinal_label(index)
        if session.started_at:
            date_part = timezone.localtime(session.started_at).strftime("%m-%d-%Y")
            label = f"{ordinal} ({date_part})"
        else:
            label = ordinal
        session_answers = list(session.answers.all())
        dashboard_trends["confidence"].append(
            _confidence_share_point(label, session_answers)
        )
        dashboard_trends["mistakes"].append(
            {"label": label, "value": mistake_counts_by_session.get(session.pk, 0)}
        )
    dashboard_trends["confidence_insight"] = build_confidence_insight(
        dashboard_trends["confidence"]
    )

    return {
        "sessions_completed": sessions.count(),
        "total_answers": total_answers,
        "accuracy": accuracy,
        "avg_confidence": round(avg_confidence, 1),
        "review_hours": review_hours,
        "accuracy_trend": accuracy_trend,
        "dashboard_trends": dashboard_trends,
        "weak_topics": weak_topics,
        "follow_ups": follow_ups,
        "calibration_matrix": matrix,
        "recent_sessions": ordered_sessions[:10],
        "session_history_rows": build_session_history_rows(session_list),
        "confidence_performance_series": build_confidence_performance_series(
            session_list
        ),
        "confidence_stacks": confidence_stacks,
        "confidence_group_by": confidence_group_by,
        "subjects_taken": subjects_taken,
        "subjects_taken_count": len(subjects_taken),
        "subjects_label": (
            f"{len(subjects_taken)} subject{'s' if len(subjects_taken) != 1 else ''} taken"
            if subjects_taken
            else "—"
        ),
        "high_avg_confidence_rate": high_avg_rate,
        "last_session_date": last_session.started_at if last_session else None,
        "calibration_max": max(matrix.values()) if total_answers else 1,
        "dominant_tier": max(matrix, key=matrix.get) if total_answers else "none",
    }


def student_course_summary(student: User, course: Course) -> dict:
    """Performance summary scoped to a student's activity in a course offering."""
    sessions = ReviewSession.objects.filter(
        student=student,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    ).select_related("topic", "topic__subject")
    answers = _course_answers(course, student=student)
    return _build_student_activity_summary(
        student,
        sessions,
        answers,
        weak_topics_filter=Q(question__topic__subject__program=course.program),
        confidence_group_by="topic",
    )


def student_subject_summary(student: User, subject) -> dict:
    """Performance summary for a student across a curriculum subject."""
    sessions = (
        ReviewSession.objects.filter(
            student=student,
            status=ReviewSession.Status.COMPLETED,
        )
        .filter(
            Q(subjects=subject)
            | Q(topic__subject=subject)
            | Q(course__code=subject.code, course__program=subject.program)
            | Q(answers__question__topic__subject=subject)
        )
        .distinct()
        .select_related("topic", "topic__subject")
    )
    answers = _subject_answers(subject, student=student)
    return _build_student_activity_summary(
        student,
        sessions,
        answers,
        weak_topics_filter=Q(question__topic__subject=subject),
        confidence_group_by="topic",
    )


def student_section_summary(student: User, section) -> dict:
    """Performance summary for a student within a ProgramSection (any subject)."""
    sessions = ReviewSession.objects.filter(
        student=student,
        student__section=section,
        status=ReviewSession.Status.COMPLETED,
    ).select_related("topic", "topic__subject")
    answers = _section_answers(section, student=student)
    return _build_student_activity_summary(
        student,
        sessions,
        answers,
        weak_topics_filter=Q(student__section=section),
        confidence_group_by="subject",
    )

def _subject_answers(subject, student: User | None = None):
    qs = Answer.objects.filter(question__topic__subject=subject)
    if student:
        qs = qs.filter(session__student=student)
    return qs


def _subject_student_ids(subject):
    return (
        Answer.objects.filter(question__topic__subject=subject)
        .values_list("session__student_id", flat=True)
        .distinct()
    )


def subject_performance_summary(subject) -> dict:
    """Aggregate analytics for a curriculum subject across all year levels."""
    student_ids = _subject_student_ids(subject)
    answers = _subject_answers(subject)
    sessions = ReviewSession.objects.filter(
        Q(subjects=subject) | Q(topic__subject=subject) | Q(course__code=subject.code),
        status=ReviewSession.Status.COMPLETED,
    ).distinct()

    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    accuracy_trend = list(
        sessions.annotate(date=TruncDate("started_at"))
        .values("date")
        .annotate(
            total=Count("answers", filter=Q(answers__question__topic__subject=subject)),
            correct=Count(
                "answers",
                filter=Q(
                    answers__question__topic__subject=subject,
                    answers__is_correct=True,
                ),
            ),
        )
        .order_by("date")
    )
    # Prefer answer-based daily trend for multi-subject sessions
    daily = list(
        answers.annotate(date=TruncDate("created"))
        .values("date")
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
        .order_by("date")
    )
    for item in daily:
        total = item["total"]
        item["accuracy"] = round(item["correct"] / total * 100, 1) if total else 0.0
        item["date"] = item["date"].isoformat() if item["date"] else ""

    for item in accuracy_trend:
        total = item["total"]
        item["accuracy"] = round(item["correct"] / total * 100, 1) if total else 0.0
        item["date"] = item["date"].isoformat() if item["date"] else ""

    year_breakdown = list(
        answers.values("session__student__year_level__name", "session__student__year_level__order")
        .annotate(
            student_count=Count("session__student_id", distinct=True),
            answer_count=Count("id"),
            correct_count=Count("id", filter=Q(is_correct=True)),
        )
        .order_by("session__student__year_level__order")
    )
    for row in year_breakdown:
        total = row["answer_count"]
        row["accuracy"] = round(row["correct_count"] / total * 100, 1) if total else 0.0
        row["year_name"] = row["session__student__year_level__name"] or "Unknown"

    calibration_matrix = confidence_tier_matrix(answers)
    misconception_topic_list = misconception_topics(answers)

    return {
        "subject": subject,
        "enrolled_count": student_ids.count(),
        "sessions_completed": sessions.count(),
        "accuracy": accuracy,
        "total_answers": total_answers,
        "accuracy_trend": daily or accuracy_trend,
        "year_breakdown": year_breakdown,
        "calibration_matrix": calibration_matrix,
        "misconception_topics": misconception_topic_list,
    }


def get_subject_roster_summaries(subject) -> list[dict]:
    """Students (any year) who answered questions for this subject."""
    student_ids = list(_subject_student_ids(subject))
    students = (
        User.objects.filter(pk__in=student_ids)
        .select_related("year_level", "section")
        .order_by("year_level__order", "last_name", "email")
    )
    answers = _subject_answers(subject)
    roster = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        total = student_answers.count()
        correct = student_answers.filter(is_correct=True).count()
        accuracy = round(correct / total * 100, 1) if total else 0.0
        avg_conf = student_answers.aggregate(avg=Avg("confidence"))["avg"] or 0
        sessions_count = (
            ReviewSession.objects.filter(student=student)
            .filter(
                Q(subjects=subject)
                | Q(topic__subject=subject)
                | Q(answers__question__topic__subject=subject)
            )
            .distinct()
            .count()
        )
        roster.append(
            {
                "student": student,
                "sessions_completed": sessions_count,
                "accuracy": accuracy,
                "avg_confidence": round(avg_conf, 1),
                "year_level": student.year_level.name if student.year_level_id else "",
                "section_label": (
                    student.section.display_label if student.section_id else ""
                ),
            }
        )
    return roster

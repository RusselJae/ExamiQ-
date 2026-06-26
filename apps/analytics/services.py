"""Analytics and performance aggregation services."""

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate

from apps.analytics.confidence import (
    CLASSIFICATION_LABELS,
    confidence_accuracy_matrix,
    misconception_topics,
)
from apps.analytics.models import MistakeRecord
from apps.questions.models import Question, Topic
from apps.reviews.models import Answer, FeedbackView, ReviewSession
from apps.users.constants import home_programs_for_department, students_in_department
from apps.users.models import Course, Program, User


def log_mistake(student: User, question: Question, answer: Answer) -> MistakeRecord:
    """Create a mistake record when a student answers incorrectly."""
    error_type = None
    if answer.selected_choice_id and answer.selected_choice.error_type_id:
        error_type = answer.selected_choice.error_type
    elif answer.selected_choice_id:
        from apps.ai.factory import get_error_classifier

        error_type = get_error_classifier().classify(question, answer)
    return MistakeRecord.objects.create(
        student=student,
        question=question,
        topic=question.topic,
        answer=answer,
        error_type=error_type,
    )


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

    recent_sessions = sessions.select_related("topic").order_by("-started_at")[:10]

    return {
        "sessions_completed": sessions.count(),
        "total_answers": total_answers,
        "accuracy": accuracy,
        "avg_confidence": round(avg_confidence, 1),
        "accuracy_trend": accuracy_trend,
        "weak_topics": weak_topics,
        "recent_sessions": recent_sessions,
    }


def topic_progress_summary(student: User) -> list[dict]:
    """Return per-topic accuracy stats for a student."""
    rows = (
        Answer.objects.filter(session__student=student)
        .values("question__topic__name")
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
                "total": total,
                "correct": row["correct"],
                "accuracy": accuracy,
            }
        )
    return results


def professor_overview_summary(professor: User) -> dict:
    """Return cross-course KPIs for a professor."""
    from django.db.models import Max
    from django.utils import timezone

    from apps.reviews.models import ReviewWindow

    courses = Course.objects.filter(professor=professor, is_archived=False)
    answers = Answer.objects.filter(session__course__professor=professor)
    total_answers = answers.count()
    correct_answers = answers.filter(is_correct=True).count()
    accuracy = round(correct_answers / total_answers * 100, 1) if total_answers else 0.0

    now = timezone.now()
    week_ago = now - timezone.timedelta(days=7)
    active_windows = ReviewWindow.objects.filter(
        course__professor=professor,
        course__is_archived=False,
        is_active=True,
        opens_at__lte=now,
        closes_at__gte=now,
    ).count()

    last_activity_at = (
        ReviewSession.objects.filter(course__professor=professor)
        .aggregate(last=Max("started_at"))
        .get("last")
    )
    total_sessions = ReviewSession.objects.filter(
        course__professor=professor,
        status__in=[ReviewSession.Status.COMPLETED, ReviewSession.Status.EXPIRED],
    ).count()

    return {
        "course_count": courses.count(),
        "student_count": ReviewSession.objects.filter(course__professor=professor)
        .values("student")
        .distinct()
        .count(),
        "accuracy": accuracy,
        "sessions_this_week": ReviewSession.objects.filter(
            course__professor=professor,
            started_at__gte=week_ago,
        ).count(),
        "active_windows": active_windows,
        "total_sessions": total_sessions,
        "as_of": now,
        "week_start": week_ago,
        "week_end": now,
        "last_activity_at": last_activity_at,
        "sessions_subtext": f"{total_sessions} total",
    }


def professor_overview_course_cards(professor: User) -> list[dict]:
    """Return per-course stats for the professor overview page."""
    from django.utils import timezone

    from apps.reviews.models import ReviewWindow

    now = timezone.now()
    week_ago = now - timezone.timedelta(days=7)
    courses = Course.objects.filter(professor=professor, is_archived=False).select_related("program")

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

        active_windows = ReviewWindow.objects.filter(
            course=course,
            is_active=True,
            opens_at__lte=now,
            closes_at__gte=now,
        ).count()

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
                "active_windows": active_windows,
                "last_session_at": last_session_at,
            }
        )
    return cards


def pending_question_review_count(chairperson: User) -> int:
    """Return pending question count for a chairperson's department."""
    department = chairperson.department
    if not department:
        return 0
    return Question.objects.filter(
        status=Question.Status.PENDING,
        topic__subject__program__managing_department=department,
    ).count()


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
        .annotate(avg_confidence=Avg("confidence"), total=Count("id"))
        .order_by("question__topic__name")
    )

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

    calibration_matrix = confidence_accuracy_matrix(answers)
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


def student_course_summary(student: User, course: Course) -> dict:
    """Performance summary scoped to a student's activity in a course offering."""
    sessions = ReviewSession.objects.filter(
        student=student,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    ).select_related("topic")
    answers = _course_answers(course, student=student)

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

    weak_topics = list(
        MistakeRecord.objects.filter(student=student, question__topic__subject__program=course.program)
        .values("topic__name")
        .annotate(mistake_count=Count("id"))
        .order_by("-mistake_count")[:5]
    )

    return {
        "sessions_completed": sessions.count(),
        "total_answers": total_answers,
        "accuracy": accuracy,
        "avg_confidence": round(avg_confidence, 1),
        "review_hours": review_hours,
        "accuracy_trend": accuracy_trend,
        "weak_topics": weak_topics,
        "calibration_matrix": confidence_accuracy_matrix(answers),
        "recent_sessions": sessions.order_by("-started_at")[:10],
    }


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


def get_topic_mastery_heatmap(course: Course) -> dict:
    """Build topic×quadrant heatmap data for a course."""
    from apps.analytics.confidence import classify_answer

    answers = _course_answers(course).select_related("question__topic")
    topic_map: dict[int, dict] = {}

    for answer in answers:
        topic = answer.question.topic
        if topic.id not in topic_map:
            topic_map[topic.id] = {
                "topic_id": topic.id,
                "topic_name": topic.name,
                "mastery": 0,
                "misconception": 0,
                "lucky_guess": 0,
                "expected_gap": 0,
                "uncertain": 0,
                "total": 0,
            }
        classification = classify_answer(answer.confidence, answer.is_correct)
        topic_map[topic.id][classification] += 1
        topic_map[topic.id]["total"] += 1

    topics = sorted(topic_map.values(), key=lambda t: t["topic_name"])
    callouts = {
        "overconfident": [t for t in topics if t["misconception"] >= 2],
        "anxious": [t for t in topics if t["lucky_guess"] >= 2],
    }

    student_rows = _build_student_heatmap_rows(course, answers)

    return {
        "topics": topics,
        "student_rows": student_rows,
        "classification_labels": CLASSIFICATION_LABELS,
        "callouts": callouts,
        "matrix": confidence_accuracy_matrix(answers),
    }


def _build_student_heatmap_rows(course: Course, answers) -> list[dict]:
    """Per-student dominant calibration quadrant counts."""
    from apps.analytics.confidence import classify_answer

    student_ids = _course_student_ids(course)
    students = User.objects.filter(pk__in=student_ids)
    rows = []
    for student in students:
        student_answers = answers.filter(session__student=student)
        counts = {
            "mastery": 0,
            "misconception": 0,
            "lucky_guess": 0,
            "expected_gap": 0,
            "uncertain": 0,
        }
        for answer in student_answers:
            counts[classify_answer(answer.confidence, answer.is_correct)] += 1
        dominant = max(counts, key=counts.get) if student_answers.exists() else "uncertain"
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
        avg_confidence = student_answers.aggregate(avg=Avg("confidence"))["avg"] or 0
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

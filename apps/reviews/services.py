from django.utils import timezone

from django.conf import settings

from apps.analytics.services import log_mistake
from apps.questions.models import Question, Topic
from apps.questions.services import count_available_questions, grade_answer
from apps.reviews.models import Answer, FeedbackView, ReviewSession, ReviewWindow, StepFeedbackView
from apps.users.models import User


class SessionExpiredError(Exception):
    """Raised when a review session has expired."""


class WindowStartError(Exception):
    """Raised when a review window cannot be used to start a session."""


def start_review_session(
    student,
    topic,
    difficulty: str,
    duration_minutes: int = 15,
    course=None,
    review_window=None,
    mode: str | None = None,
    seconds_per_question: int | None = None,
    pre_session_confidence: str = "",
    session_goal: str = "",
    question_queue: list[int] | None = None,
    subjects=None,
) -> ReviewSession:
    """Create a new active review session."""
    if review_window:
        mode = mode or review_window.mode
        if seconds_per_question is None:
            seconds_per_question = review_window.seconds_per_question
        duration_minutes = review_window.duration_minutes
    mode = mode or ReviewSession.Mode.TIMED_EXAM
    if seconds_per_question is None:
        seconds_per_question = getattr(settings, "DEFAULT_SECONDS_PER_QUESTION", 30)
    queue = list(question_queue or [])
    if queue:
        planned_question_count = len(queue)
    else:
        planned_question_count = count_available_questions(topic, difficulty)
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        seconds_per_question=seconds_per_question,
        mode=mode,
        status=ReviewSession.Status.ACTIVE,
        course=course,
        review_window=review_window,
        planned_question_count=planned_question_count,
        question_queue=queue,
        pre_session_confidence=pre_session_confidence,
        session_goal=session_goal,
    )
    if subjects:
        session.subjects.set(subjects)
    from apps.core.audit import log_audit_event
    from apps.core.models import AuditLog

    log_audit_event(
        student,
        AuditLog.Action.SESSION_START,
        target_user=student,
        message=f"Started exam on {topic.name} ({difficulty})",
        target_type="ReviewSession",
        target_id=session.pk,
    )
    return session


def start_session_from_window(
    student: User,
    window: ReviewWindow,
    topic: Topic | None = None,
) -> ReviewSession:
    """Start a session directly from a scheduled review window."""
    if student.role == User.Role.STUDENT and not student.home_degree_program:
        raise WindowStartError("Set your home degree program in Profile before starting a review.")

    if not window.is_open:
        raise WindowStartError("This review window is no longer open.")

    if (
        student.home_degree_program
        and window.course.program.slug != student.home_degree_program
    ):
        raise WindowStartError("This review window is not available for your program.")

    allowed_topics = (
        window.topics.all()
        if window.topics.exists()
        else Topic.objects.filter(subject__program=window.course.program)
    )
    if topic:
        if not allowed_topics.filter(pk=topic.pk).exists():
            raise WindowStartError("Selected topic is not allowed for this review window.")
    else:
        topic = allowed_topics.order_by("name").first()
        if not topic:
            raise WindowStartError("No topics are available for this review window.")

    difficulties = window.allowed_difficulties or [Question.Difficulty.EASY]
    difficulty = difficulties[0]

    return start_review_session(
        student=student,
        topic=topic,
        difficulty=difficulty,
        duration_minutes=window.duration_minutes,
        course=window.course,
        review_window=window,
        mode=window.mode,
        seconds_per_question=window.seconds_per_question,
    )


def validate_session_active(session: ReviewSession) -> None:
    """Ensure session is still active and not expired."""
    if session.status != ReviewSession.Status.ACTIVE:
        raise SessionExpiredError("This session is no longer active.")
    if session.mode == ReviewSession.Mode.TIMED_EXAM:
        return
    if session.is_expired:
        session.status = ReviewSession.Status.EXPIRED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])
        raise SessionExpiredError("Time is up. Session expired.")


def submit_answer(
    session: ReviewSession,
    question,
    confidence: int | None = None,
    selected_choice=None,
    numeric_response: str = "",
    time_spent_seconds: int = 0,
    timed_out: bool = False,
) -> Answer:
    """Grade and record a student's answer."""
    validate_session_active(session)

    is_correct, _ = grade_answer(
        question,
        submitted_value=numeric_response,
        selected_choice=selected_choice,
    )

    answer = Answer.objects.create(
        session=session,
        question=question,
        selected_choice=selected_choice,
        numeric_response=numeric_response,
        confidence=confidence,
        is_correct=is_correct,
        timed_out=timed_out,
        time_spent_seconds=time_spent_seconds,
    )

    if not is_correct:
        log_mistake(
            student=session.student,
            question=question,
            answer=answer,
            generate_ai=False,
        )

    from apps.reviews.tutor_services import clear_tutor_conversation_on_reanswer

    clear_tutor_conversation_on_reanswer(
        session.student,
        question,
        exclude_answer_pk=answer.pk,
    )

    return answer


def record_feedback_view(answer: Answer) -> FeedbackView:
    """Track when a student views step-by-step explanation."""
    return FeedbackView.objects.create(answer=answer)


def record_step_feedback_view(answer: Answer, explanation_step) -> StepFeedbackView:
    """Track when a student views a specific explanation step."""
    return StepFeedbackView.objects.create(answer=answer, explanation_step=explanation_step)


def complete_session(session: ReviewSession) -> ReviewSession:
    """Mark a review session as completed."""
    if session.status == ReviewSession.Status.ACTIVE:
        session.status = ReviewSession.Status.COMPLETED
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])
        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        log_audit_event(
            session.student,
            AuditLog.Action.SESSION_COMPLETE,
            target_user=session.student,
            message=f"Completed exam on {session.topic.name}",
            target_type="ReviewSession",
            target_id=session.pk,
        )
    return session


def get_answered_question_ids(session: ReviewSession) -> list[int]:
    """Return IDs of questions already answered in this session."""
    return list(session.answers.values_list("question_id", flat=True))


def get_next_queued_question(session: ReviewSession):
    """Return the next unanswered question from the session queue, if any."""
    queue = session.question_queue or []
    if not queue:
        return None
    answered = set(get_answered_question_ids(session))
    for question_id in queue:
        if question_id not in answered:
            return (
                Question.objects.filter(pk=question_id)
                .select_related("topic__subject")
                .prefetch_related("choices", "explanation_steps")
                .first()
            )
    return None


def session_has_more_questions(session: ReviewSession) -> bool:
    """Whether the session still has unanswered questions available."""
    if session.question_queue:
        answered = set(get_answered_question_ids(session))
        return any(qid not in answered for qid in session.question_queue)
    from apps.questions.services import get_adaptive_questions_for_session

    answered_ids = get_answered_question_ids(session)
    return get_adaptive_questions_for_session(
        session.student,
        session.topic,
        session.difficulty,
        count=1,
        exclude_ids=answered_ids,
    ).exists()

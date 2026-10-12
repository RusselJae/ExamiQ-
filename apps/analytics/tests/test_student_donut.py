"""Student dashboard donut aggregates."""

import pytest

from apps.analytics.services import (
    professor_confidence_donut,
    student_incorrect_question_series,
    student_performance_donut,
    student_professor_summary,
)
from apps.questions.models import Question
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.services import start_review_session


@pytest.mark.django_db
def test_student_performance_donut_counts(
    student, topic, mcq_question, numeric_question
):
    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["status"])
    Answer.objects.create(
        session=session,
        question=question,
        confidence=5,
        is_correct=True,
    )
    Answer.objects.create(
        session=session,
        question=numeric_question,
        confidence=1,
        is_correct=False,
    )
    donut = student_performance_donut(student)
    assert donut["total"] == 2
    by_key = {s["key"]: s for s in donut["slices"]}
    assert by_key["sure_correct"]["value"] == 1
    assert by_key["guessing_incorrect"]["value"] == 1
    assert by_key["sure_correct"]["percent"] == 50.0
    assert donut["session_count"] == 1
    assert donut["percent_correct"] == 50.0
    assert "1 answer" in donut["scope_line"] or "2 answers" in donut["scope_line"]
    assert donut["insight"]
    assert "confidence=" in donut["insight_url"]

    period_donut = student_performance_donut(student, period="7")
    assert period_donut["period"] == "7"
    assert "scope_line" in period_donut


@pytest.mark.django_db
def test_faculty_donut_drops_student_area_link(
    student, professor, topic, mcq_question, numeric_question
):
    """Faculty must not be sent a student-area mistake-log URL."""
    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["status"])
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=session,
        question=numeric_question,
        confidence=5,
        is_correct=False,
    )

    faculty_donut = student_performance_donut(student, for_professor=True)
    assert faculty_donut["insight_url"] == ""
    assert "this student" in faculty_donut["insight"]
    # Same numbers as the student-facing donut.
    assert faculty_donut["total"] == student_performance_donut(student)["total"]


@pytest.mark.django_db
def test_professor_summary_includes_donut_payload(
    professor, course, student, topic, mcq_question
):
    """Faculty student detail renders the donut from summary.dashboard_trends."""
    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.course = course
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["course", "status"])
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    summary = student_professor_summary(student, professor)
    donut = summary["dashboard_trends"]["donut"]
    assert donut["total"] == 1
    assert donut["slices"]
    assert donut["scope_line"]
    # Per-question mistakes stay available for the mistakes bar chart.
    assert isinstance(summary["dashboard_trends"]["mistakes"], list)


@pytest.mark.django_db
def test_mistake_series_exposes_session_for_ai_tutor(
    professor, course, student, topic, mcq_question
):
    """The bar chart opens the AI Tutor, which needs session + answer ids."""
    from apps.analytics.models import MistakeRecord

    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.course = course
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["course", "status"])
    answer = Answer.objects.create(
        session=session, question=question, confidence=3, is_correct=False
    )
    MistakeRecord.objects.create(
        student=student,
        answer=answer,
        question=question,
        topic=question.topic,
    )

    points = student_incorrect_question_series(student)
    assert points
    point = points[0]
    assert point["answer_id"] == answer.pk
    assert point["session_id"] == session.pk
    assert point["url"]


@pytest.mark.django_db
def test_professor_confidence_donut_spans_scope(
    professor, course, student, topic, mcq_question, numeric_question
):
    """Overview donut aggregates every answer in the professor's courses."""
    from apps.users.models import Course as CourseModel

    question, _correct = mcq_question
    other_student = type(student)(
        email="other@test.edu",
        role=student.role,
        department=student.department,
    )
    other_student.set_password("testpass123")
    other_student.save()

    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    other_session = ReviewSession.objects.create(
        student=other_student,
        topic=topic,
        difficulty=question.difficulty,
        course=CourseModel.objects.get(pk=course.pk),
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=other_session,
        question=numeric_question,
        confidence=1,
        is_correct=False,
    )

    donut = professor_confidence_donut(professor)
    assert donut["total"] == 2
    by_key = {s["key"]: s for s in donut["slices"]}
    assert by_key["sure_correct"]["value"] == 1
    assert by_key["guessing_incorrect"]["value"] == 1
    assert donut["session_count"] == 2
    assert donut["percent_correct"] == 50.0
    # Faculty view never links into the student area.
    assert donut["insight_url"] == ""
    assert "students" in donut["insight"] or donut["insight"] == ""
    assert "2 answers" in donut["scope_line"]


@pytest.mark.django_db
def test_professor_confidence_donut_period_filter(
    professor, course, student, topic, mcq_question
):
    """The 7/30/all switcher narrows the donut to recent sessions."""
    from datetime import timedelta

    from django.utils import timezone

    question, _correct = mcq_question

    old_session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    recent_session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    # started_at is auto_now_add, so backdate after insert.
    ReviewSession.objects.filter(pk=old_session.pk).update(
        started_at=timezone.now() - timedelta(days=45)
    )
    Answer.objects.create(
        session=old_session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=recent_session, question=question, confidence=1, is_correct=False
    )

    all_time = professor_confidence_donut(professor)
    assert all_time["total"] == 2
    assert all_time["period"] == "all"
    # All-time shows the observed date span, not a fixed label.
    assert "2 answers" in all_time["scope_line"]

    seven = professor_confidence_donut(professor, period="7")
    assert seven["total"] == 1
    assert seven["period"] == "7"
    assert "Last 7 days" in seven["scope_line"]
    assert seven["session_count"] == 1

    thirty = professor_confidence_donut(professor, period="30")
    assert thirty["total"] == 1
    assert thirty["period"] == "30"
    assert "Last 30 days" in thirty["scope_line"]

    # Unknown values fall back to all-time rather than erroring.
    assert professor_confidence_donut(professor, period="bogus")["total"] == 2


@pytest.mark.django_db
def test_professor_confidence_donut_excludes_other_professors(
    professor, course, student, topic, mcq_question, chairperson
):
    """Answers outside the professor's courses must not appear."""
    from apps.users.models import Course as CourseModel
    from apps.users.models import Program as ProgramModel

    question, _correct = mcq_question
    other_program = ProgramModel.objects.get(pk=course.program_id)
    other_course = CourseModel.objects.create(
        program=other_program,
        code="OTH101",
        name="Other professor course",
        professor=chairperson,
        term="1st Sem",
        academic_year="2026",
        section="Z",
    )
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=other_course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    donut = professor_confidence_donut(professor)
    assert donut["total"] == 0
    assert donut["slices"]
    assert donut["insight"] == ""

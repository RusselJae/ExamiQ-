"""Student dashboard donut aggregates."""

import pytest

from apps.analytics.services import student_performance_donut
from apps.questions.models import Question
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.services import start_review_session


@pytest.mark.django_db
def test_student_performance_donut_counts(student, topic, mcq_question, numeric_question):
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

"""Tests for system revisions: publish, bank cap, validation, retakes."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import override_settings

from apps.questions.models import Question, QuestionValidationSession
from apps.questions.services import (
    assert_subject_bank_has_capacity,
    publish_question_as_faculty,
    subject_bank_slots_remaining,
)
from apps.questions.validation_session_services import (
    clamp_validation_size,
    start_validation_session,
)
from apps.reviews.models import RetakeActionPlan, ReviewSession
from apps.reviews.retake_services import (
    can_start_retake,
    completed_attempt_count,
    requires_action_plan,
)


@pytest.mark.django_db
def test_publish_question_as_faculty_sets_approved(mcq_question, professor):
    question, _choice = mcq_question
    question.status = Question.Status.DRAFT
    question.is_active = False
    question.explanation_status = "draft"
    question.save()
    publish_question_as_faculty(question, professor, approve_explanations=True)
    question.refresh_from_db()
    assert question.status == Question.Status.APPROVED
    assert question.is_active is True
    assert question.validated_by_id == professor.pk


@pytest.mark.django_db
@override_settings(MAX_QUESTIONS_PER_SUBJECT=2)
def test_subject_bank_cap_blocks_extra(subject, topic, professor):
    for i in range(2):
        Question.objects.create(
            topic=topic,
            stem=f"Cap question {i}",
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.IDENTIFICATION,
            expected_answer="x",
            status=Question.Status.DRAFT,
            proposed_by=professor,
        )
    assert subject_bank_slots_remaining(subject) == 0
    with pytest.raises(ValueError, match="max 2"):
        assert_subject_bank_has_capacity(subject, additional=1)


@pytest.mark.django_db
def test_validation_session_size_clamped(subject, topic, professor, mcq_question):
    question, _choice = mcq_question
    question.status = Question.Status.APPROVED
    question.is_active = True
    question.save(update_fields=["status", "is_active"])
    assert clamp_validation_size(5) == 10
    assert clamp_validation_size(25) == 20
    assert clamp_validation_size(15) == 15
    session = start_validation_session(
        faculty=professor, subject=subject, topic=topic, size=15
    )
    assert isinstance(session, QuestionValidationSession)
    assert session.size == 1  # only one approved question available
    assert session.items.count() == 1


@pytest.mark.django_db
@override_settings(RETAKE_ACTION_PLAN_THRESHOLD=3)
def test_retake_requires_action_plan_after_threshold(
    student, topic, teaching_assignment, mcq_question
):
    _question, _choice = mcq_question
    course = teaching_assignment.course
    for _ in range(3):
        ReviewSession.objects.create(
            student=student,
            topic=topic,
            course=course,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            status=ReviewSession.Status.COMPLETED,
        )
    assert completed_attempt_count(
        student, course=course, subject=topic.subject, difficulty="easy"
    ) == 3
    assert requires_action_plan(
        student, course=course, subject=topic.subject, difficulty="easy"
    )
    allowed, plan = can_start_retake(
        student, course=course, subject=topic.subject, difficulty="easy"
    )
    assert allowed is False
    assert isinstance(plan, RetakeActionPlan)

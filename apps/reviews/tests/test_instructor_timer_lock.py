"""Instructor-configured exam timer locks student Start Review."""

import pytest

from apps.reviews.exam_setup_services import (
    instructor_locked_seconds_for_subjects,
    sync_program_subject_timers,
)


@pytest.mark.django_db
def test_instructor_lock_when_subjects_configured(subject):
    program = subject.program
    assert program is not None
    sync_program_subject_timers(
        program,
        subject_ids=[subject.pk],
        timers_by_subject_id={subject.pk: 45},
        default_seconds=30,
    )
    assert instructor_locked_seconds_for_subjects([subject]) == 45


@pytest.mark.django_db
def test_no_lock_when_program_has_no_selected_subjects(subject):
    program = subject.program
    sync_program_subject_timers(
        program,
        subject_ids=[],
        timers_by_subject_id={},
        default_seconds=30,
    )
    assert instructor_locked_seconds_for_subjects([subject]) is None

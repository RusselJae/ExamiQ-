"""Exam setup helpers for faculty and student flows."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable

from apps.questions.models import Question, Subject, Topic
from apps.reviews.models import DEFAULT_EXAM_DIFFICULTIES, ExamSetup, SectionExamSetup
from apps.users.models import Course, User

QUESTIONS_PER_SUBJECT = 10
MIN_EXAM_SUBJECTS = 1


def get_or_create_exam_setup(course) -> ExamSetup:
    """Ensure every course offering has an exam setup record."""
    setup, created = ExamSetup.objects.get_or_create(
        course=course,
        defaults={
            "is_enabled": True,
            "allowed_difficulties": list(DEFAULT_EXAM_DIFFICULTIES),
        },
    )
    if created:
        return setup
    if not setup.allowed_difficulties:
        setup.allowed_difficulties = list(DEFAULT_EXAM_DIFFICULTIES)
        setup.save(update_fields=["allowed_difficulties"])
    return setup


def student_setup_eligibility(student: User) -> dict:
    """Return eligibility flags and messages for the exam setup page.

    Year/section are identity-only: students must have them set, but exams are
    open across all BSED Math subjects with approved questions.
    """
    if student.home_degree_program != User.HomeDegreeProgram.BSED_MATH:
        return {
            "eligible": False,
            "reason": "program",
            "message": "Exam practice is available for BSEd Mathematics students.",
        }
    if not student.section_id:
        return {
            "eligible": False,
            "reason": "section",
            "message": "Set your section in Profile before starting an exam.",
        }
    if not student.year_level_id:
        return {
            "eligible": False,
            "reason": "year_level",
            "message": "Set your year level in Profile before starting an exam.",
        }
    if student.section.year_level_id != student.year_level_id:
        return {
            "eligible": False,
            "reason": "year_mismatch",
            "message": "Your year level does not match your section. Update your Profile.",
        }
    if not program_has_approved_questions():
        return {
            "eligible": False,
            "reason": "no_questions",
            "message": "No approved questions are available yet. Check back later.",
        }
    setup = section_exam_setup_for_student(student)
    if setup is not None and not setup.is_enabled:
        return {
            "eligible": False,
            "reason": "section_disabled",
            "message": "Exams are disabled for your section right now. Check back later.",
        }
    return {"eligible": True}


def section_exam_setup_for_student(student: User) -> SectionExamSetup | None:
    if not student.section_id:
        return None
    return (
        SectionExamSetup.objects.filter(section_id=student.section_id)
        .prefetch_related("subjects")
        .first()
    )


def get_or_create_section_exam_setup(section) -> SectionExamSetup:
    setup, created = SectionExamSetup.objects.get_or_create(
        section=section,
        defaults={
            "is_enabled": True,
            "allowed_difficulties": list(DEFAULT_EXAM_DIFFICULTIES),
        },
    )
    if created:
        return setup
    if not setup.allowed_difficulties:
        setup.allowed_difficulties = list(DEFAULT_EXAM_DIFFICULTIES)
        setup.save(update_fields=["allowed_difficulties"])
    return setup


def subjects_available_for_student(student: User | None = None):
    """BSED Math subjects; restricted when section exam setup exists and is enabled."""
    qs = (
        Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH)
        .select_related("year_level", "program")
        .order_by("year_level__order", "semester", "code")
    )
    if student is None or not student.section_id:
        return qs
    setup = section_exam_setup_for_student(student)
    if setup is None:
        return qs
    if not setup.is_enabled:
        return Subject.objects.none()
    selected_ids = list(setup.subjects.values_list("pk", flat=True))
    if not selected_ids:
        return qs
    return qs.filter(pk__in=selected_ids)


def program_has_approved_questions() -> bool:
    return Question.objects.filter(
        topic__subject__program__slug=User.HomeDegreeProgram.BSED_MATH,
        status=Question.Status.APPROVED,
        is_active=True,
    ).exists()



def topics_for_open_subject(subject: Subject):
    """Top-level topics under a subject (open bank; no section gating)."""
    return Topic.objects.filter(subject=subject, parent__isnull=True).order_by("name")


def course_for_subject(subject: Subject) -> Course | None:
    """Prefer a faculty course offering matching the subject code."""
    return (
        Course.objects.filter(
            program=subject.program,
            code=subject.code,
            is_archived=False,
        )
        .order_by("-academic_year", "term")
        .first()
    )


def exam_seconds_per_question(course) -> int:
    """Return per-question time limit from exam setup."""
    if course is None:
        from django.conf import settings

        return getattr(settings, "DEFAULT_SECONDS_PER_QUESTION", 30)
    setup = get_or_create_exam_setup(course)
    return setup.seconds_per_question


def exam_timing_for_course(course) -> tuple[int, int]:
    """Return (duration_minutes, seconds_per_question) from exam setup."""
    if course is None:
        from django.conf import settings

        seconds = getattr(settings, "DEFAULT_SECONDS_PER_QUESTION", 30)
        return 30, seconds
    setup = get_or_create_exam_setup(course)
    return setup.duration_minutes, setup.seconds_per_question


def resolve_exam_target(student: User, subject: Subject, difficulty: str) -> dict | None:
    """Pick a topic under subject with the most questions at difficulty."""
    from apps.questions.services import count_available_questions

    best = None
    best_count = 0
    for topic in topics_for_open_subject(subject):
        count = count_available_questions(topic, difficulty)
        if count > best_count:
            best_count = count
            course = course_for_subject(subject)
            best = {
                "topic": topic,
                "difficulty": difficulty,
                "course": course,
                "subject": subject,
                "question_count": count,
                "seconds_per_question": exam_seconds_per_question(course),
            }
    return best


def build_multi_subject_exam_target(
    student: User,
    subjects: Iterable[Subject],
    difficulty: str,
) -> dict:
    """Build a shuffled question queue across multiple subjects.

    Raises ValueError with a user-facing message when validation fails.
    """
    from apps.questions.services import (
        count_available_questions_for_subject,
        question_ids_for_subject,
    )

    subject_list = list(subjects)
    if len(subject_list) < MIN_EXAM_SUBJECTS:
        raise ValueError(f"Select at least {MIN_EXAM_SUBJECTS} courses.")

    weak: list[str] = []
    for subject in subject_list:
        if count_available_questions_for_subject(subject, difficulty) < 1:
            weak.append(subject.code)
    if weak:
        codes = ", ".join(weak)
        raise ValueError(
            f"No approved questions at this difficulty for: {codes}. "
            "Pick other courses or another difficulty."
        )

    queue: list[int] = []
    primary_topic = None
    for subject in subject_list:
        ids = question_ids_for_subject(
            subject, difficulty, limit=QUESTIONS_PER_SUBJECT
        )
        queue.extend(ids)
        if primary_topic is None:
            target = resolve_exam_target(student, subject, difficulty)
            if target:
                primary_topic = target["topic"]

    if not queue:
        raise ValueError("No approved questions available for the selected courses.")

    random.shuffle(queue)

    first_subject = subject_list[0]
    course = course_for_subject(first_subject)
    seconds = exam_seconds_per_question(course)
    duration_minutes = max(1, math.ceil(len(queue) * seconds / 60))

    if primary_topic is None:
        primary_topic = topics_for_open_subject(first_subject).first()
    if primary_topic is None:
        raise ValueError("Selected courses have no topics yet.")

    return {
        "topic": primary_topic,
        "subjects": subject_list,
        "difficulty": difficulty,
        "course": course,
        "question_queue": queue,
        "question_count": len(queue),
        "seconds_per_question": seconds,
        "duration_minutes": duration_minutes,
    }


def resolve_auto_exam_target(student: User) -> dict | None:
    """Fallback: best subject/topic/difficulty combo for preview cards."""
    from apps.questions.models import Question as QModel

    best = None
    best_count = 0
    for subject in subjects_available_for_student(student):
        for difficulty in QModel.Difficulty.values:
            target = resolve_exam_target(student, subject, difficulty)
            if target and target["question_count"] > best_count:
                best_count = target["question_count"]
                best = target
    return best


def student_has_auto_exam(student: User) -> bool:
    """Whether the student can start an exam."""
    return student_setup_eligibility(student).get("eligible", False)


# Backwards-compatible aliases used by older imports
def enabled_assignments_for_student(student: User):
    from apps.users.models import TeachingAssignment

    return TeachingAssignment.objects.none()


def assignment_for_student_subject(student: User, subject: Subject):
    return None


def topics_for_student_subject(student: User, subject: Subject):
    return topics_for_open_subject(subject)


def difficulties_for_student_subject(student: User, subject: Subject) -> list[str]:
    return list(DEFAULT_EXAM_DIFFICULTIES)

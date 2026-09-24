"""Exam setup helpers for faculty and student flows."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable

from apps.questions.models import Question, Subject, Topic
from apps.reviews.models import (
    DEFAULT_EXAM_DIFFICULTIES,
    ExamSetup,
    ProgramExamSetup,
    SectionExamSetup,
)
from apps.users.models import Course, Program, User

QUESTIONS_PER_SUBJECT = 10
MIN_EXAM_SUBJECTS = 1
MIN_QUESTIONS_PER_SUBJECT = 3
MAX_QUESTIONS_SINGLE_SUBJECT = 20
MAX_TOTAL_QUESTIONS = 100


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


def get_or_create_program_exam_setup(program: Program | None = None) -> ProgramExamSetup:
    """Ensure BSED Math (or given program) has a program-wide exam setup."""
    if program is None:
        program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
    if program is None:
        raise ValueError("BSED Math program is not configured.")
    setup, created = ProgramExamSetup.objects.get_or_create(
        program=program,
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

    Eligibility checks program, year level, year-matched subjects, and questions.
    """
    if student.home_degree_program != User.HomeDegreeProgram.BSED_MATH:
        return {
            "eligible": False,
            "reason": "program",
            "message": "Exam practice is available for BSEd Mathematics students.",
        }
    if not student.year_level_id:
        return {
            "eligible": False,
            "reason": "no_year_level",
            "message": (
                "Your year level is not set. Contact your department to update "
                "your profile before starting an exam."
            ),
        }
    year_subjects = subjects_available_for_student(student)
    if not year_subjects.exists():
        return {
            "eligible": False,
            "reason": "no_year_subjects",
            "message": (
                "No course subjects are available for your year level yet. "
                "Check back later."
            ),
        }
    if not year_has_approved_questions(student):
        return {
            "eligible": False,
            "reason": "no_questions",
            "message": (
                "No approved questions are available for your year level yet. "
                "Check back later."
            ),
        }
    return {"eligible": True}


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


def _program_exam_subject_base():
    """BSED Math subjects open for student exams (all years)."""
    return (
        Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH)
        .select_related("year_level", "program")
        .order_by("year_level__order", "semester", "code")
    )


def subjects_available_for_student(student: User | None = None):
    """BSED Math subjects open for student exams (program exam setup + year).

    When a student is provided, only subjects matching that student's year
    level are returned. Students without a year level get an empty queryset.
    """
    base = _program_exam_subject_base()
    if student is not None:
        if not student.year_level_id:
            return base.none()
        return base.filter(year_level_id=student.year_level_id)
    return base


def other_subjects_available_for_student(student: User | None = None):
    """Program exam subjects outside the student's year level (optional add-ons)."""
    base = _program_exam_subject_base()
    if student is None or not student.year_level_id:
        return base.none()
    return base.exclude(year_level_id=student.year_level_id)

def program_has_approved_questions() -> bool:
    return Question.objects.filter(
        topic__subject__program__slug=User.HomeDegreeProgram.BSED_MATH,
        status=Question.Status.APPROVED,
        is_active=True,
    ).exists()


def year_has_approved_questions(student: User) -> bool:
    """Whether approved questions exist for the student's year-scoped subjects."""
    subject_ids = list(
        subjects_available_for_student(student).values_list("pk", flat=True)
    )
    if not subject_ids:
        return False
    return Question.objects.filter(
        topic__subject_id__in=subject_ids,
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


def ensure_catalog_course_for_subject(subject: Subject) -> Course:
    """Ensure a catalog Course shell exists for per-subject exam timers."""
    from apps.users.section_services import get_current_academic_year

    existing = course_for_subject(subject)
    if existing:
        return existing

    academic_year = get_current_academic_year()
    ay_label = academic_year.label if academic_year else "2025-2026"
    course, _ = Course.objects.get_or_create(
        code=subject.code,
        program=subject.program,
        term="Catalog",
        academic_year=ay_label,
        section="Catalog",
        defaults={
            "name": subject.name,
            "is_archived": False,
        },
    )
    if course.name != subject.name:
        course.name = subject.name
        course.save(update_fields=["name"])
    return course


def subject_exam_timer_seconds(subject: Subject, *, default_seconds: int = 30) -> int:
    """Read per-subject timer from catalog course ExamSetup, else default."""
    course = course_for_subject(subject)
    if course is None:
        return default_seconds
    return get_or_create_exam_setup(course).seconds_per_question


def program_subject_timer_rows(program: Program) -> list[dict]:
    """Rows for faculty exam-setup UI: subject, selected flag, timer seconds."""
    setup = get_or_create_program_exam_setup(program)
    default_seconds = setup.seconds_per_question or 30
    selected_ids = set(setup.subjects.values_list("pk", flat=True))
    rows = []
    for subject in (
        Subject.objects.filter(program=program)
        .select_related("year_level")
        .order_by("year_level__order", "semester", "code")
    ):
        rows.append(
            {
                "subject": subject,
                "selected": subject.pk in selected_ids,
                "seconds": subject_exam_timer_seconds(
                    subject, default_seconds=default_seconds
                ),
            }
        )
    return rows


def sync_program_subject_timers(
    program: Program,
    *,
    subject_ids: list[int],
    timers_by_subject_id: dict[int, int],
    default_seconds: int = 30,
) -> ProgramExamSetup:
    """Save program subject selection and per-subject exam timers."""
    setup = get_or_create_program_exam_setup(program)
    setup.is_enabled = True
    setup.seconds_per_question = default_seconds
    setup.save(update_fields=["is_enabled", "seconds_per_question"])

    subjects = list(
        Subject.objects.filter(program=program, pk__in=subject_ids).order_by(
            "year_level__order", "semester", "code"
        )
    )
    setup.subjects.set(subjects)

    for subject in subjects:
        seconds = timers_by_subject_id.get(subject.pk, default_seconds)
        if not 10 <= seconds <= 120:
            raise ValueError(
                f"Timer for {subject.code} must be between 10 and 120 seconds."
            )
        course = ensure_catalog_course_for_subject(subject)
        exam_setup = get_or_create_exam_setup(course)
        exam_setup.seconds_per_question = seconds
        exam_setup.save(update_fields=["seconds_per_question"])

    return setup


def exam_seconds_per_question(course) -> int:
    """Return per-question time limit from course setup, else program setup."""
    if course is not None:
        setup = get_or_create_exam_setup(course)
        return setup.seconds_per_question
    try:
        program_setup = get_or_create_program_exam_setup()
        return program_setup.seconds_per_question
    except ValueError:
        from django.conf import settings

        return getattr(settings, "DEFAULT_SECONDS_PER_QUESTION", 30)


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
    *,
    question_types: list[str] | None = None,
    seconds_per_question: int | None = None,
    questions_per_subject: int | None = None,
) -> dict:
    """Build a shuffled question queue across multiple subjects.

    Each selected subject contributes a randomized number of questions:
    - at least MIN_QUESTIONS_PER_SUBJECT (or all available if fewer)
    - at most MAX_QUESTIONS_SINGLE_SUBJECT for a single subject
    - total across all subjects capped at MAX_TOTAL_QUESTIONS

    Raises ValueError with a user-facing message when validation fails.
    """
    from apps.questions.models import Question
    from apps.questions.services import (
        count_available_questions_for_subject,
        question_ids_for_subject,
    )

    subject_list = list(subjects)
    if len(subject_list) < MIN_EXAM_SUBJECTS:
        raise ValueError(
            f"At least {MIN_EXAM_SUBJECTS} course subject(s) must be available "
            "for your year level."
        )

    types = list(question_types or [])
    type_labels: list[str] = []
    for value in types:
        try:
            type_labels.append(Question.QuestionType(value).label)
        except ValueError:
            type_labels.append(value.replace("_", " "))
    type_label = ", ".join(type_labels)

    weak: list[str] = []
    for subject in subject_list:
        if (
            count_available_questions_for_subject(
                subject, difficulty, question_types=types
            )
            < 1
        ):
            weak.append(subject.code)
    if weak:
        codes = ", ".join(weak)
        if type_label:
            raise ValueError(
                f"No approved {type_label} questions at this difficulty for: {codes}. "
                "Try another difficulty or other question types."
            )
        raise ValueError(
            f"No approved questions at this difficulty for: {codes}. "
            "Try another difficulty."
        )

    avail = [
        count_available_questions_for_subject(
            s, difficulty, question_types=types
        )
        for s in subject_list
    ]

    if questions_per_subject is not None:
        target_q = max(1, min(int(questions_per_subject), MAX_QUESTIONS_SINGLE_SUBJECT))
        caps = [min(a, MAX_QUESTIONS_SINGLE_SUBJECT) for a in avail]
        per_subject = [min(target_q, caps[i]) for i in range(len(subject_list))]
        total_q = sum(per_subject)
        if total_q > MAX_TOTAL_QUESTIONS:
            budget = MAX_TOTAL_QUESTIONS
            scaled = []
            for count in per_subject:
                take = min(count, budget)
                scaled.append(take)
                budget -= take
            per_subject = scaled
    else:
        floors = [min(MIN_QUESTIONS_PER_SUBJECT, a) for a in avail]

        if len(subject_list) == 1:
            cap = min(avail[0], MAX_QUESTIONS_SINGLE_SUBJECT)
            per_subject = [random.randint(floors[0], cap)]
        else:
            caps = [min(a, MAX_QUESTIONS_SINGLE_SUBJECT) for a in avail]
            if sum(caps) <= MAX_TOTAL_QUESTIONS:
                per_subject = [random.randint(floors[i], caps[i]) for i in range(len(subject_list))]
            else:
                per_subject = list(floors)
                budget = MAX_TOTAL_QUESTIONS - sum(floors)
                order = list(range(len(subject_list)))
                random.shuffle(order)
                idx = 0
                while budget > 0:
                    i = order[idx % len(order)]
                    if per_subject[i] < caps[i]:
                        per_subject[i] += 1
                        budget -= 1
                    if all(per_subject[j] >= caps[j] for j in range(len(subject_list))):
                        break
                    idx += 1

    queue: list[int] = []
    primary_topic = None
    for i, subject in enumerate(subject_list):
        ids = question_ids_for_subject(
            subject,
            difficulty,
            limit=per_subject[i],
            question_types=types,
        )
        queue.extend(ids)
        if primary_topic is None:
            target = resolve_exam_target(student, subject, difficulty)
            if target:
                primary_topic = target["topic"]

    if not queue:
        raise ValueError(
            "No approved questions available for your year-level course subjects."
        )

    random.shuffle(queue)

    first_subject = subject_list[0]
    course = course_for_subject(first_subject)
    if seconds_per_question is not None:
        seconds = int(seconds_per_question)
        if seconds != 0 and not 10 <= seconds <= 120:
            seconds = exam_seconds_per_question(course)
    else:
        seconds = exam_seconds_per_question(course)
    duration_minutes = (
        0 if seconds == 0 else max(1, math.ceil(len(queue) * seconds / 60))
    )

    if primary_topic is None:
        primary_topic = topics_for_open_subject(first_subject).first()
    if primary_topic is None:
        raise ValueError("Your year-level course subjects have no topics yet.")

    return {
        "topic": primary_topic,
        "subjects": subject_list,
        "difficulty": difficulty,
        "question_types": types,
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

"""Exam setup helpers for faculty and student flows."""

from __future__ import annotations

from apps.questions.models import Subject, Topic
from apps.reviews.models import DEFAULT_EXAM_DIFFICULTIES, ExamSetup
from apps.users.models import AcademicTerm, TeachingAssignment, User


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
    """Return eligibility flags and messages for the exam setup page."""
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
    current_term = AcademicTerm.get_current()
    if not current_term:
        return {
            "eligible": False,
            "reason": "term",
            "message": "No active academic term is configured. Check back later.",
        }
    return {"eligible": True, "current_term": current_term}


def enabled_assignments_for_student(student: User):
    """Teaching assignments with enabled exam setup for the student's section."""
    eligibility = student_setup_eligibility(student)
    if not eligibility.get("eligible"):
        return TeachingAssignment.objects.none()
    current_term = eligibility["current_term"]
    return (
        TeachingAssignment.objects.filter(
            program_section=student.section,
            term=current_term,
            course__exam_setup__is_enabled=True,
        )
        .select_related(
            "course",
            "course__exam_setup",
            "subject",
            "program_section",
            "term",
        )
        .prefetch_related("course__exam_setup__topics")
    )


def assignment_for_student_subject(student: User, subject: Subject):
    """Return the teaching assignment linking student to subject, if any."""
    return enabled_assignments_for_student(student).filter(subject=subject).first()


def topics_for_student_subject(student: User, subject: Subject):
    """Topics available for a subject given exam setup rules."""
    assignment = assignment_for_student_subject(student, subject)
    if not assignment:
        return Topic.objects.none()
    setup = assignment.course.exam_setup
    base = Topic.objects.filter(subject=subject, parent__isnull=True)
    if setup.topics.exists():
        return base.filter(pk__in=setup.topics.values_list("pk", flat=True))
    return base


def difficulties_for_student_subject(student: User, subject: Subject) -> list[str]:
    """Allowed difficulty levels for a subject."""
    assignment = assignment_for_student_subject(student, subject)
    if not assignment:
        return []
    return assignment.course.exam_setup.effective_difficulties()

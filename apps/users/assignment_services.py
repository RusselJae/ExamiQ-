"""Chairperson teaching assignment services."""

from django.db import transaction

from apps.questions.curriculum import subjects_for_teaching_assignment, term_semester
from apps.questions.models import Subject
from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.users.models import Course, ProgramSection, TeachingAssignment, User


def get_assigned_subject_ids(professor: User) -> set[int]:
    """Return subject PKs the professor is assigned to teach."""
    return set(
        TeachingAssignment.objects.filter(professor=professor).values_list(
            "subject_id", flat=True
        )
    )


def professor_has_assignments(professor: User) -> bool:
    return TeachingAssignment.objects.filter(professor=professor).exists()


def professor_can_access_subject(professor: User, subject) -> bool:
    assigned_ids = get_assigned_subject_ids(professor)
    if not assigned_ids:
        return True
    return subject.pk in assigned_ids


def get_professor_course_queryset(professor: User):
    """Courses from teaching assignments, falling back to legacy self-created courses."""
    assignment_courses = Course.objects.filter(
        teaching_assignment__professor=professor,
        is_archived=False,
    )
    if assignment_courses.exists():
        return assignment_courses
    return Course.objects.filter(professor=professor, is_archived=False)


def get_assigned_subjects_queryset(professor: User, program_id: int):
    """Subjects the professor may teach; scoped when assignments exist."""
    from apps.questions.models import Subject

    assigned_ids = get_assigned_subject_ids(professor)
    if assigned_ids:
        return Subject.objects.filter(pk__in=assigned_ids, program_id=program_id)
    return Subject.objects.filter(program_id=program_id)


def professor_has_assignment(professor: User, subject_id: int) -> bool:
    return TeachingAssignment.objects.filter(
        professor=professor,
        subject_id=subject_id,
    ).exists()


def validate_assignment_subject(section: ProgramSection, subject: Subject, term) -> None:
    """Raise ValueError when subject does not match section year and term semester."""
    if subject.program_id != section.program_id:
        raise ValueError("Subject must belong to the section's program.")
    if subject.year_level_id != section.year_level_id:
        raise ValueError(
            "Subject year level must match the section's year level."
        )
    semester = term_semester(term)
    if semester is not None and subject.semester != semester:
        raise ValueError("Subject semester must match the selected academic term.")


@transaction.atomic
def create_teaching_assignment(
    *,
    professor: User,
    program_section: ProgramSection,
    subject: Subject,
    term,
    assigned_by: User,
) -> TeachingAssignment:
    """Create a teaching assignment and linked course offering."""
    validate_assignment_subject(program_section, subject, term)

    assignment, created = TeachingAssignment.objects.get_or_create(
        professor=professor,
        program_section=program_section,
        subject=subject,
        term=term,
        defaults={"assigned_by": assigned_by},
    )
    if not created:
        return assignment

    course, _ = Course.objects.get_or_create(
        code=subject.code,
        program=program_section.program,
        term=term.name,
        academic_year=term.academic_year.label,
        section=program_section.label,
        defaults={
            "name": subject.name,
            "professor": professor,
        },
    )
    if course.professor_id != professor.pk:
        course.professor = professor
        course.save(update_fields=["professor"])

    assignment.course = course
    assignment.save(update_fields=["course"])
    get_or_create_exam_setup(course)
    return assignment

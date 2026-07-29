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


def get_professor_section_nav(professor: User) -> list[dict]:
    """Unique ProgramSection rows for the faculty sidebar (BSED Math).

    Lists all active BSED Math sections for the current academic year so empty
    cohorts still appear. Each entry links to section analytics.
    """
    from apps.users.models import Program, ProgramSection
    from apps.users.section_services import get_current_academic_year

    program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
    if not program:
        return []

    academic_year = get_current_academic_year()
    qs = (
        ProgramSection.objects.filter(program=program, is_active=True)
        .select_related("program", "year_level", "academic_year")
        .order_by("year_level__order", "label")
    )
    if academic_year:
        qs = qs.filter(academic_year=academic_year)

    return [
        {
            "label": section.display_label,
            "section": section,
            "section_id": section.pk,
        }
        for section in qs
    ]


def get_or_create_catalog_course(professor: User, subject: Subject) -> Course:
    """Ensure a professor Course offering exists for catalog subject tools."""
    from apps.users.section_services import get_current_academic_year

    academic_year = get_current_academic_year()
    ay_label = academic_year.label if academic_year else "2025-2026"
    course, _created = Course.objects.get_or_create(
        professor=professor,
        program=subject.program,
        code=subject.code,
        section="Catalog",
        term="Catalog",
        academic_year=ay_label,
        defaults={
            "name": subject.name,
            "is_archived": False,
        },
    )
    if course.name != subject.name:
        course.name = subject.name
        course.save(update_fields=["name"])
    get_or_create_exam_setup(course)
    return course


def create_catalog_subject(
    *,
    code: str,
    name: str,
    year_level,
    semester: int,
    professor: User,
) -> tuple[Subject, Course]:
    """Create a BSED Math curriculum subject + default topic + catalog Course."""
    from apps.questions.models import Topic
    from apps.users.models import Program

    program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
    if not program:
        raise ValueError("BSED Math program is not configured.")

    subject, created = Subject.objects.get_or_create(
        program=program,
        code=code.strip().upper(),
        defaults={
            "name": name.strip(),
            "year_level": year_level,
            "semester": semester,
        },
    )
    if not created:
        raise ValueError(f"Course code {subject.code} already exists.")

    Topic.objects.get_or_create(
        subject=subject,
        name=subject.name,
        defaults={"parent": None},
    )
    course = get_or_create_catalog_course(professor, subject)
    return subject, course


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
) -> tuple[TeachingAssignment, bool]:
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
        return assignment, False

    course, _ = Course.objects.get_or_create(
        code=subject.code,
        program=program_section.program,
        term=term.name,
        academic_year=term.academic_year.label,
        section=program_section.display_label,
        defaults={
            "name": subject.name,
            "professor": professor,
        },
    )
    if course.section != program_section.display_label:
        course.section = program_section.display_label
        course.save(update_fields=["section"])

    if course.professor_id != professor.pk:
        course.professor = professor
        course.save(update_fields=["professor"])

    assignment.course = course
    assignment.save(update_fields=["course"])
    get_or_create_exam_setup(course)
    return assignment, True


@transaction.atomic
def create_teaching_assignments(
    *,
    professor: User,
    program_sections,
    subject: Subject,
    term,
    assigned_by: User,
) -> dict[str, int]:
    """Create teaching assignments for multiple sections."""
    created_count = 0
    skipped_count = 0
    for program_section in program_sections:
        _, created = create_teaching_assignment(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=term,
            assigned_by=assigned_by,
        )
        if created:
            created_count += 1
        else:
            skipped_count += 1
    return {"created": created_count, "skipped": skipped_count}

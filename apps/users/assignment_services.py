"""Chairperson teaching assignment services."""

from django.db import IntegrityError, transaction

from apps.questions.curriculum import subjects_for_teaching_assignment, term_semester
from apps.questions.models import Subject
from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.users.models import Course, ProgramSection, TeachingAssignment, User


def get_assigned_subject_ids(professor: User) -> set[int]:
    """Return subject PKs the professor handles (profile first, else teaching load)."""
    profile_ids = set(professor.assigned_subjects.values_list("pk", flat=True))
    if profile_ids:
        return profile_ids
    return set(
        TeachingAssignment.objects.filter(professor=professor).values_list(
            "subject_id", flat=True
        )
    )


def get_faculty_profile_section_ids(professor: User) -> set[int]:
    """Section PKs faculty selected on their profile."""
    return set(professor.assigned_sections.values_list("pk", flat=True))


def get_faculty_profile_subject_ids(professor: User) -> set[int]:
    """Subject PKs faculty selected on their profile."""
    return set(professor.assigned_subjects.values_list("pk", flat=True))


def faculty_has_chat_scope(professor: User) -> bool:
    """Option B: both sections and subjects must be set for chat ownership."""
    return bool(
        get_faculty_profile_section_ids(professor)
        and get_faculty_profile_subject_ids(professor)
    )


def faculty_handles_student_subject(
    professor: User, *, section_id: int | None, subject_id: int | None
) -> bool:
    """True when faculty profile covers this student section and subject."""
    if not section_id or not subject_id:
        return False
    if not faculty_has_chat_scope(professor):
        return False
    return (
        section_id in get_faculty_profile_section_ids(professor)
        and subject_id in get_faculty_profile_subject_ids(professor)
    )


def professor_has_assignments(professor: User) -> bool:
    if professor.assigned_subjects.exists() or professor.assigned_sections.exists():
        return True
    return TeachingAssignment.objects.filter(professor=professor).exists()


def professor_can_access_subject(
    professor: User, subject, *, course: Course | None = None
) -> bool:
    if course and is_catalog_course(course):
        return True
    profile_ids = get_faculty_profile_subject_ids(professor)
    if profile_ids:
        return subject.pk in profile_ids
    assigned_ids = get_assigned_subject_ids(professor)
    if not assigned_ids:
        return True
    return subject.pk in assigned_ids


def get_professor_course_queryset(professor: User):
    """Courses from teaching assignments, falling back to legacy self-created courses.

    Always scoped to BSED Math subjects that still exist in the curriculum.
    """
    from apps.users.models import Program

    bsed = Program.objects.filter(slug=User.HomeDegreeProgram.BSED_MATH).first()
    keep_codes = set()
    if bsed:
        keep_codes = set(
            Subject.objects.filter(program=bsed).values_list("code", flat=True)
        )

    def _scoped(qs):
        qs = qs.filter(is_archived=False)
        if bsed:
            qs = qs.filter(program=bsed)
        if keep_codes:
            qs = qs.filter(code__in=keep_codes)
        return qs

    assignment_courses = _scoped(
        Course.objects.filter(teaching_assignment__professor=professor)
    )
    if assignment_courses.exists():
        return assignment_courses
    return _scoped(Course.objects.filter(professor=professor))


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


def is_catalog_course(course: Course) -> bool:
    """Return True when the offering is the shared subject catalog shell."""
    return (
        (course.section or "").strip() == "Catalog"
        and (course.term or "").strip() == "Catalog"
    )


def professor_can_access_course(professor: User, course: Course) -> bool:
    """Faculty may open shared catalog courses; other offerings stay professor-owned."""
    if is_catalog_course(course):
        return True
    return course.professor_id == professor.pk


def get_or_create_catalog_course(professor: User, subject: Subject) -> Course:
    """Ensure a professor Course offering exists for catalog subject tools."""
    from apps.users.section_services import get_current_academic_year

    academic_year = get_current_academic_year()
    ay_label = academic_year.label if academic_year else "2025-2026"
    lookup = {
        "code": subject.code,
        "program": subject.program,
        "term": "Catalog",
        "academic_year": ay_label,
        "section": "Catalog",
    }
    defaults = {
        "name": subject.name,
        "professor": professor,
        "is_archived": False,
    }
    try:
        course, _created = Course.objects.get_or_create(**lookup, defaults=defaults)
    except IntegrityError:
        course = Course.objects.get(**lookup)

    update_fields: list[str] = []
    if course.name != subject.name:
        course.name = subject.name
        update_fields.append("name")
    if course.is_archived:
        course.is_archived = False
        update_fields.append("is_archived")
    if update_fields:
        course.save(update_fields=update_fields)

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


def delete_catalog_subject(subject: Subject) -> str:
    """Remove a BSED Math curriculum subject and matching catalog courses.

    Cascades topics/questions via FK. Returns the deleted subject code.
    """
    if subject.program.slug != User.HomeDegreeProgram.BSED_MATH:
        raise ValueError("Only BSED Math course subjects can be removed here.")

    code = subject.code
    program = subject.program
    Course.objects.filter(
        program=program,
        code=code,
        term="Catalog",
        section="Catalog",
    ).delete()
    subject.delete()
    return code


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


def faculty_can_manage_section_student(
    professor: User,
    section: ProgramSection,
    student: User,
) -> bool:
    """True when faculty handles the section and the student belongs to it."""
    if student.role != User.Role.STUDENT:
        return False
    if student.section_id != section.pk:
        return False
    return section.pk in get_faculty_profile_section_ids(professor)


def archive_section_student(
    professor: User,
    section: ProgramSection,
    student: User,
) -> None:
    """Hide a student from rosters and block login."""
    if not faculty_can_manage_section_student(professor, section, student):
        raise PermissionError("Faculty cannot archive this student.")
    if student.is_archived:
        return
    student.is_archived = True
    student.is_active = False
    student.save(update_fields=["is_archived", "is_active"])


def restore_section_student(
    professor: User,
    section: ProgramSection,
    student: User,
) -> None:
    """Restore an archived student to active roster and login."""
    if not faculty_can_manage_section_student(professor, section, student):
        raise PermissionError("Faculty cannot restore this student.")
    if not student.is_archived:
        return
    student.is_archived = False
    student.is_active = True
    student.save(update_fields=["is_archived", "is_active"])


def professor_can_view_student(professor: User, student: User) -> bool:
    """True when faculty may open a student's detail page.

    Matches the Students roster gate: completed exams on courses they own,
    or completed exams in their assigned section/subject profile scope.
    """
    from django.db.models import Q

    from apps.reviews.models import ReviewSession

    if student.role != User.Role.STUDENT:
        return False

    completed = ReviewSession.objects.filter(
        student=student,
        status=ReviewSession.Status.COMPLETED,
    )
    if completed.filter(course__professor=professor).exists():
        return True

    if not faculty_has_chat_scope(professor):
        return False

    section_ids = get_faculty_profile_section_ids(professor)
    subject_ids = get_faculty_profile_subject_ids(professor)
    if student.section_id not in section_ids:
        return False

    return completed.filter(
        Q(subjects__in=subject_ids)
        | Q(topic__subject_id__in=subject_ids)
        | Q(
            course__code__in=Subject.objects.filter(pk__in=subject_ids).values(
                "code"
            )
        )
    ).exists()


def professor_can_view_session(professor: User, session) -> bool:
    """True when faculty may read a student's completed session summary."""
    from apps.reviews.models import Answer, ReviewSession

    if session.status not in (
        ReviewSession.Status.COMPLETED,
        ReviewSession.Status.EXPIRED,
    ):
        return False

    if session.course_id and session.course.professor_id == professor.pk:
        return True

    student = session.student
    if not student or student.role != User.Role.STUDENT:
        return False

    section_ids = get_faculty_profile_section_ids(professor)
    subject_ids = get_faculty_profile_subject_ids(professor)
    if not section_ids or not subject_ids:
        return False
    if student.section_id not in section_ids:
        return False

    if session.topic_id and session.topic.subject_id in subject_ids:
        return True
    if session.subjects.filter(pk__in=subject_ids).exists():
        return True
    return Answer.objects.filter(
        session=session,
        question__topic__subject_id__in=subject_ids,
    ).exists()

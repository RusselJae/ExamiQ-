"""Chairperson teaching assignment services."""

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.questions.models import Subject
from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.users.models import Course, ProgramSection, TeachingAssignment, User

#: At most this many distinct faculty may handle the same subject in one term.
MAX_FACULTY_PER_SUBJECT_TERM = 2

#: At most this many sections of one course a single faculty member may handle.
MAX_SECTIONS_PER_FACULTY_COURSE = 2


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
    return section_id in get_faculty_profile_section_ids(
        professor
    ) and subject_id in get_faculty_profile_subject_ids(professor)


def faculty_handled_section_ids(professor: User) -> set[int]:
    """ProgramSection PKs covered by this professor's current-year assignments."""
    from apps.users.section_services import get_current_academic_year

    current_year = get_current_academic_year()
    if current_year is None:
        return set()
    return set(
        TeachingAssignment.objects.filter(
            professor=professor,
            term__academic_year=current_year,
        ).values_list("program_section_id", flat=True)
    )


def students_enrolled_in_handled_sections(professor: User) -> set[int]:
    """Active students whose cohort section is handled by this professor."""
    section_ids = faculty_handled_section_ids(professor)
    if not section_ids:
        return set()
    return set(
        User.objects.filter(
            role=User.Role.STUDENT,
            section_id__in=section_ids,
            is_active=True,
            is_archived=False,
        ).values_list("id", flat=True)
    )


def students_with_exams_on_handled_subjects(professor: User) -> set[int]:
    """Active, non-archived students with completed exams on handled subjects.

    Restores the pre-section-removal visibility path: students enrolled in a
    section the professor handles (via teaching assignments) who sat a
    completed exam touching one of the handled subjects. Lets learners who
    answered exams before an explicit handled link existed stay visible.
    """
    from apps.reviews.models import ReviewSession

    handled_ids = handled_subject_ids(professor)
    section_ids = faculty_handled_section_ids(professor)
    if not handled_ids or not section_ids:
        return set()
    return set(
        ReviewSession.objects.filter(
            status=ReviewSession.Status.COMPLETED,
            student__is_active=True,
            student__is_archived=False,
            student__section_id__in=section_ids,
        )
        .filter(Q(topic__subject_id__in=handled_ids) | Q(subjects__in=handled_ids))
        .values_list("student_id", flat=True)
        .distinct()
    )


def students_visible_to_faculty(professor: User) -> set[int]:
    """Student IDs this faculty member may see in analytics.

    The single canonical scope for every faculty-facing count: students with a
    StudentFacultyAssignment to this professor in the current academic year
    (active, non-archived students only), plus section-enrolled students with
    completed exams on handled subjects (the pre-section-removal visibility
    path). Callers add their own session/status filters on top.
    """
    from apps.users.models import StudentFacultyAssignment
    from apps.users.section_services import get_current_academic_year

    current_year = get_current_academic_year()
    if not current_year:
        return set()
    assigned_ids = set(
        StudentFacultyAssignment.objects.filter(
            faculty=professor,
            academic_year=current_year,
            student__is_active=True,
            student__is_archived=False,
        ).values_list("student_id", flat=True)
    )
    return (
        assigned_ids
        | students_enrolled_in_handled_sections(professor)
        | students_with_exams_on_handled_subjects(professor)
    )


def handled_subject_ids(professor: User) -> set[int]:
    """Subject PKs this professor handles.

    TeachingAssignment rows win when present; otherwise fall back to the
    faculty profile's selected subjects. Subjects with assigned students
    (StudentFacultyAssignment) are always included, since visibility follows
    handled students — e.g. a student who picked this faculty at signup.
    """
    from apps.users.models import StudentFacultyAssignment
    from apps.users.section_services import get_current_academic_year

    ta_ids = set(
        TeachingAssignment.objects.filter(professor=professor).values_list(
            "subject_id", flat=True
        )
    )
    if ta_ids:
        handled = set(ta_ids)
    else:
        handled = set(get_faculty_profile_subject_ids(professor))
    year = get_current_academic_year()
    if year is not None:
        handled |= set(
            StudentFacultyAssignment.objects.filter(
                faculty=professor, academic_year=year
            ).values_list("subject_id", flat=True)
        )
    return handled


def handled_subjects_for_faculty(professor: User):
    """Subjects this professor handles, ordered for display."""
    from apps.questions.models import Subject

    ids = handled_subject_ids(professor)
    if not ids:
        return Subject.objects.none()
    qs = Subject.objects.filter(pk__in=ids).select_related("program", "year_level")
    from apps.users.models import Program

    program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
    if program is not None:
        qs = qs.filter(program=program)
    return qs.order_by("year_level__order", "code")


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
    return (course.section or "").strip() == "Catalog" and (
        course.term or ""
    ).strip() == "Catalog"


def professor_can_access_course(professor: User, course: Course) -> bool:
    """Faculty may open shared catalog courses; other offerings stay professor-owned."""
    if is_catalog_course(course):
        return True
    return course.professor_id == professor.pk


def get_or_create_catalog_course(professor: User | None, subject: Subject) -> Course:
    """Ensure a shared catalog Course offering exists for subject tools."""
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


def create_curriculum_subject(
    *,
    program,
    code: str,
    name: str,
    year_level,
    semester: int,
    banner=None,
) -> Subject:
    """Create a coordinator-managed curriculum subject and its catalog shell."""
    from apps.questions.models import Topic

    subject = Subject.objects.create(
        program=program,
        code=code.strip().upper(),
        name=name.strip(),
        year_level=year_level,
        semester=semester,
        banner=banner or "",
    )
    Topic.objects.create(subject=subject, name=subject.name, parent=None)
    get_or_create_catalog_course(None, subject)
    return subject


def delete_curriculum_subject(subject: Subject) -> str:
    """Remove a curriculum subject and its matching catalog shell courses.

    Cascades topics/questions via FK. Returns the deleted subject code.
    """
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


def validate_assignment_subject(
    section: ProgramSection, subject: Subject, term
) -> None:
    """Raise ValueError when subject does not match the section's program/year.

    Semester is intentionally ignored so any course can be assigned in any term.
    """
    if subject.program_id != section.program_id:
        raise ValueError("Subject must belong to the section's program.")
    if subject.year_level_id != section.year_level_id:
        raise ValueError("Subject year level must match the section's year level.")


def _assert_faculty_slot_available(subject, term, professor: User) -> None:
    """Cap distinct faculty per subject+term so the form shows an error.

    Raises ValueError (surfaced as a form message by the callers) when two
    other faculty already handle this subject for the term.
    """
    holder_ids = set(
        TeachingAssignment.objects.filter(subject=subject, term=term)
        .exclude(professor=professor)
        .values_list("professor_id", flat=True)
    )
    if len(holder_ids) >= MAX_FACULTY_PER_SUBJECT_TERM:
        raise ValueError(
            f"Only up to {MAX_FACULTY_PER_SUBJECT_TERM} faculty members can "
            f"handle {subject.code} for this term."
        )


def _assert_section_slot_available(
    professor: User, subject, term, program_section
) -> None:
    """Cap a faculty member at two sections of the same course per term.

    Raises ValueError (surfaced as a form message by the callers) when the
    professor already handles two *other* sections of this subject.
    """
    held_ids = set(
        TeachingAssignment.objects.filter(
            professor=professor, subject=subject, term=term
        )
        .exclude(program_section=program_section)
        .values_list("program_section_id", flat=True)
    )
    if len(held_ids) >= MAX_SECTIONS_PER_FACULTY_COURSE:
        raise ValueError(
            f"Faculty can handle at most {MAX_SECTIONS_PER_FACULTY_COURSE} "
            f"sections of {subject.code} per term."
        )


def create_teaching_assignment(
    *,
    professor: User,
    program_section: ProgramSection,
    subject: Subject,
    term,
    assigned_by: User,
) -> tuple[TeachingAssignment, bool]:
    """Create a teaching assignment and linked course offering.

    Assignments are one row per (professor, subject, term, section). A faculty
    member may hold at most two sections of the same course in a term; the
    same section returns the existing row instead of creating a duplicate.
    """
    existing = TeachingAssignment.objects.filter(
        professor=professor,
        subject=subject,
        term=term,
        program_section=program_section,
    ).first()
    if existing is not None:
        return existing, False

    conflict = (
        TeachingAssignment.objects.filter(
            subject=subject,
            term=term,
            program_section=program_section,
        )
        .exclude(professor=professor)
        .select_related("professor")
        .first()
    )
    if conflict is not None:
        holder = conflict.professor.get_full_name() or conflict.professor.email
        raise ValueError(
            f"{program_section.display_label} is already assigned to {holder} "
            f"for {subject.code}. Reassign that section instead."
        )

    _assert_faculty_slot_available(subject, term, professor)
    _assert_section_slot_available(professor, subject, term, program_section)
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


@transaction.atomic
def reassign_teaching_assignment(
    assignment: TeachingAssignment, *, professor: User
) -> TeachingAssignment:
    """Move a teaching assignment to a different professor.

    Used when next year's (or this year's) teaching load changes hands.
    Raises ValueError when the target professor already holds the identical
    (section, subject, term) assignment. The linked course offering follows
    the new professor only when it still points at the old one.
    """
    if professor.pk == assignment.professor_id:
        return assignment
    _assert_faculty_slot_available(assignment.subject, assignment.term, professor)
    _assert_section_slot_available(
        professor,
        assignment.subject,
        assignment.term,
        assignment.program_section,
    )
    conflict = (
        TeachingAssignment.objects.filter(
            professor=professor,
            subject=assignment.subject,
            term=assignment.term,
            program_section=assignment.program_section,
        )
        .exclude(pk=assignment.pk)
        .exists()
    )
    if conflict:
        raise ValueError("That professor already handles this course section.")
    old_professor_id = assignment.professor_id
    assignment.professor = professor
    assignment.save(update_fields=["professor"])
    course = assignment.course
    if course is not None and course.professor_id == old_professor_id:
        course.professor = professor
        course.save(update_fields=["professor"])
    return assignment


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
    archive_user(student)


def restore_section_student(
    professor: User,
    section: ProgramSection,
    student: User,
) -> None:
    """Restore an archived student to active roster and login."""
    if not faculty_can_manage_section_student(professor, section, student):
        raise PermissionError("Faculty cannot restore this student.")
    restore_user(student)


def archive_user(user: User) -> None:
    """Archive an account: hide from active lists and block login."""
    if user.is_archived:
        return
    user.is_archived = True
    user.is_active = False
    user.save(update_fields=["is_archived", "is_active"])


def restore_user(user: User) -> None:
    """Restore an archived account to active login."""
    if not user.is_archived:
        return
    user.is_archived = False
    user.is_active = True
    user.save(update_fields=["is_archived", "is_active"])


def faculty_assigned_section_labels(user: User, *, limit: int = 8) -> list[str]:
    """Return compact section labels for a faculty member's teaching assignments."""
    if user.role != User.Role.PROFESSOR:
        return []
    qs = (
        TeachingAssignment.objects.filter(professor=user)
        .select_related(
            "program_section__program",
            "program_section__year_level",
            "program_section__academic_year",
            "term__academic_year",
        )
        .order_by(
            "-term__academic_year__label",
            "program_section__year_level__order",
            "program_section__label",
        )
    )
    labels: list[str] = []
    seen: set[str] = set()
    for assignment in qs:
        section = assignment.program_section
        label = section.display_label
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def annotate_users_with_section_labels(users) -> None:
    """Attach ``assigned_section_labels`` list onto each user in ``users``."""
    professor_ids = [u.pk for u in users if u.role == User.Role.PROFESSOR]
    by_prof: dict[int, list[str]] = {pk: [] for pk in professor_ids}
    if professor_ids:
        assignments = (
            TeachingAssignment.objects.filter(professor_id__in=professor_ids)
            .select_related(
                "program_section__program",
                "program_section__year_level",
                "program_section__academic_year",
            )
            .order_by(
                "professor_id",
                "program_section__year_level__order",
                "program_section__label",
            )
        )
        seen: dict[int, set[str]] = {pk: set() for pk in professor_ids}
        for assignment in assignments:
            pid = assignment.professor_id
            label = assignment.program_section.display_label
            if label in seen[pid]:
                continue
            seen[pid].add(label)
            if len(by_prof[pid]) < 8:
                by_prof[pid].append(label)
    for user in users:
        if user.role == User.Role.PROFESSOR:
            user.assigned_section_labels = by_prof.get(user.pk, [])
        elif user.role == User.Role.STUDENT and user.section_id:
            user.assigned_section_labels = [user.section.display_label]
        else:
            user.assigned_section_labels = []


def annotate_users_with_course_labels(users) -> None:
    """Attach ``assigned_course_labels`` list onto each user in ``users``.

    Students show the courses they are currently taking: enrolled subjects
    for irregular students, every curriculum subject of their year level for
    regular students. Faculty show the subjects they handle.
    """
    professor_ids = [u.pk for u in users if u.role == User.Role.PROFESSOR]
    by_prof: dict[int, list[str]] = {pk: [] for pk in professor_ids}
    if professor_ids:
        assignments = (
            TeachingAssignment.objects.filter(professor_id__in=professor_ids)
            .select_related("subject")
            .order_by("professor_id", "subject__code")
        )
        seen: dict[int, set[str]] = {pk: set() for pk in professor_ids}
        for assignment in assignments:
            pid = assignment.professor_id
            code = assignment.subject.code
            if code in seen[pid]:
                continue
            seen[pid].add(code)
            if len(by_prof[pid]) < 8:
                by_prof[pid].append(code)

    for user in users:
        if user.role == User.Role.PROFESSOR:
            user.assigned_course_labels = by_prof.get(user.pk, [])
            continue
        if user.role != User.Role.STUDENT:
            user.assigned_course_labels = []
            continue
        subjects = _student_course_subjects(user)
        user.assigned_course_labels = [s.code for s in subjects[:8]]


def _student_course_subjects(user) -> list:
    """Subjects making up a student's current course load."""
    from apps.questions.models import Subject
    from apps.users.models import IrregularSubjectEnrollment

    if user.is_irregular:
        year = None
        try:
            from apps.users.section_services import get_current_academic_year

            year = get_current_academic_year()
        except Exception:  # noqa: BLE001 - no-year configured is non-fatal
            year = None
        enrollments = IrregularSubjectEnrollment.objects.filter(
            student=user, status="enrolled"
        ).select_related("subject")
        if year is not None:
            enrollments = enrollments.filter(term__academic_year=year)
        subjects = [e.subject for e in enrollments if e.subject_id is not None]
        subjects = sorted(subjects, key=lambda s: s.code or "")
        return [s for s in subjects if s.program_id]
    if not user.year_level_id:
        return []
    program = None
    try:
        from apps.users.models import Program

        program = Program.for_home_degree(user.home_degree_program)
    except Exception:  # noqa: BLE001 - unknown mapping falls back to year-level
        program = None
    qs = Subject.objects.filter(year_level_id=user.year_level_id).order_by("code")
    if program is not None:
        qs = qs.filter(program=program)
    return list(qs)


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

    if student.pk in students_visible_to_faculty(professor):
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
        | Q(course__code__in=Subject.objects.filter(pk__in=subject_ids).values("code"))
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

    if student.pk in students_visible_to_faculty(professor):
        return True

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

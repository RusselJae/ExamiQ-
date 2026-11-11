"""User profile services."""

from allauth.account.adapter import get_adapter
from allauth.account.internal.flows.manage_email import email_already_exists
from allauth.account.models import EmailAddress
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.questions.models import Subject
from apps.users.models import User


def count_active_sessions(user: User) -> int:
    """Return the number of non-expired sessions for this user."""
    user_id = str(user.pk)
    count = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get("_auth_user_id") == user_id:
            count += 1
    return count


def get_account_activity(user: User) -> dict:
    """Return display values for the profile account activity card."""
    password_changed_at = user.password_changed_at or user.date_joined
    session_count = count_active_sessions(user)
    device_label = "device" if session_count == 1 else "devices"
    return {
        "last_login": user.last_login,
        "password_changed_at": password_changed_at,
        "active_session_count": session_count,
        "active_session_label": f"{session_count} {device_label}",
    }


def get_student_subjects(
    student: User, term_id: int | None = None
) -> QuerySet[Subject]:
    """Return the subjects a student is enrolled in for a given term.

    Regular students get subjects from their cohort section's curriculum
    (section → year_level → program). Irregular students get subjects from
    their ``IrregularSubjectEnrollment`` records (subject × section × term).

    This is the single access point used by exam setup, review windows,
    rosters, and analytics so both student types behave consistently.
    """
    if not student or student.role != User.Role.STUDENT:
        return Subject.objects.none()

    if student.is_irregular:
        qs = Subject.objects.filter(
            irregular_enrollments__student=student,
            irregular_enrollments__status="enrolled",
        ).distinct()
        if term_id:
            qs = qs.filter(irregular_enrollments__term_id=term_id)
        return qs.select_related("program", "year_level").order_by(
            "program__name", "year_level__order", "code"
        )

    # Regular student: subjects via section → year_level → curriculum
    if not student.section_id or not student.year_level_id:
        return Subject.objects.none()
    return (
        Subject.objects.filter(
            program=student.section.program_id,
            year_level=student.year_level_id,
        )
        .distinct()
        .select_related("program", "year_level")
        .order_by("program__name", "year_level__order", "code")
    )


def request_email_change(request: HttpRequest, user: User, new_email: str) -> str:
    """Request an email change via allauth verification; does not update user.email yet."""
    adapter = get_adapter()
    email, _already_exists = email_already_exists(new_email, user=user)

    if email == user.email.lower():
        raise ValidationError("This is already your login email.")

    EmailAddress.objects.add_new_email(request, user, email)
    return "Check your inbox to confirm the new email."


def _current_academic_year():
    from apps.users.models import AcademicYear

    return AcademicYear.get_current()


def subject_faculty_options(
    subject_ids: list[int], *, section_id: int | None = None
) -> dict[int, list[dict]]:
    """Faculty teaching each subject this academic year, with teaching load.

    Each option carries the faculty pk, display name, section label, current
    enrolled-student count, and section capacity ("load" shown in the signup
    picker, e.g. "12/40 slots"). Only faculty with a TeachingAssignment for
    the subject in the current academic year are listed. When ``section_id``
    is given (regular students who picked a cohort section), only faculty
    handling that section are returned.
    """
    from django.db.models import Count

    from apps.users.models import StudentFacultyAssignment, TeachingAssignment

    options: dict[int, list[dict]] = {pk: [] for pk in subject_ids}
    if not subject_ids:
        return options
    current_year = _current_academic_year()

    assignments = (
        TeachingAssignment.objects.filter(subject_id__in=subject_ids)
        .select_related("professor", "program_section", "term__academic_year")
        .order_by("professor__first_name", "professor__last_name")
    )
    if current_year is not None:
        assignments = assignments.filter(term__academic_year=current_year)
    if section_id:
        assignments = assignments.filter(program_section_id=section_id)

    by_triple: dict[tuple[int, int, int], dict] = {}
    for row in assignments:
        key = (row.subject_id, row.professor_id, row.program_section_id)
        entry = by_triple.get(key)
        if entry is None:
            name = row.professor.get_full_name() or row.professor.email
            entry = {
                "faculty_pk": row.professor_id,
                "name": name,
                "section_id": row.program_section_id,
                "section_label": (row.program_section.display_label or "").strip(),
                "enrolled": 0,
                "capacity": row.program_section.max_students or 0,
            }
            by_triple[key] = entry
            options[row.subject_id].append(entry)
        else:
            entry["capacity"] += row.program_section.max_students or 0

    if current_year is not None:
        counts = (
            StudentFacultyAssignment.objects.filter(
                subject_id__in=subject_ids, academic_year=current_year
            )
            .values("subject_id", "faculty_id")
            .annotate(total=Count("student_id", distinct=True))
        )
        for row in counts:
            for entry in options.get(row["subject_id"], []):
                if entry["faculty_pk"] == row["faculty_id"]:
                    entry["enrolled"] = row["total"]

    # Fallback: subjects with no teaching assignment still show every
    # program faculty member so the signup picker never renders an empty
    # group (e.g. fresh DB before chairperson assigns loads). Picks remain
    # valid because form validation skips subjects without options only
    # when there is genuinely no faculty in the system.
    from apps.users.models import User as _User

    missing_ids = [pk for pk in subject_ids if not options.get(pk)]
    if missing_ids and not section_id:
        program_ids = list(
            Subject.objects.filter(pk__in=missing_ids).values_list(
                "program_id", flat=True
            )
        )
        fallback_faculty = (
            _User.objects.filter(role=_User.Role.PROFESSOR)
            .filter(
                Q(department__managed_programs__in=program_ids)
                | Q(teaching_assignments__subject__program_id__in=program_ids)
            )
            .distinct()
            .order_by("first_name", "last_name")
        )
        if not fallback_faculty.exists():
            fallback_faculty = _User.objects.filter(role=_User.Role.PROFESSOR).order_by(
                "first_name", "last_name"
            )
        for pk in missing_ids:
            options[pk] = [
                {
                    "faculty_pk": fac.pk,
                    "name": fac.get_full_name() or fac.email,
                    "section_id": None,
                    "section_label": "",
                    "enrolled": 0,
                    "capacity": 0,
                }
                for fac in fallback_faculty
            ]
    return options


def filter_subject_catalog(queryset, params) -> object:
    """Apply code/name search plus program, year-level, and semester filters."""
    search = (params.get("q") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(code__icontains=search) | Q(name__icontains=search)
        )
    program_id = params.get("program", "")
    if str(program_id).isdigit():
        queryset = queryset.filter(program_id=int(program_id))
    year_level_id = params.get("year_level", "")
    if str(year_level_id).isdigit():
        queryset = queryset.filter(year_level_id=int(year_level_id))
    semester = params.get("semester", "")
    if str(semester).isdigit():
        queryset = queryset.filter(semester=int(semester))
    return queryset


def catalog_filter_context(params) -> dict:
    """Normalized filter values plus a has-active flag for the catalog UI."""
    search_query = (params.get("q") or "").strip()
    program_filter = params.get("program", "")
    year_level_filter = params.get("year_level", "")
    semester_filter = params.get("semester", "")
    return {
        "search_query": search_query,
        "program_filter": program_filter,
        "year_level_filter": year_level_filter,
        "semester_filter": semester_filter,
        "filter_has_active": bool(
            search_query
            or str(program_filter).isdigit()
            or str(year_level_filter).isdigit()
            or str(semester_filter).isdigit()
        ),
    }


def attach_subject_stats(subjects: list) -> None:
    """Attach faculty/student/question/material counts to subject objects."""
    from django.db.models import Count

    from apps.ai.models import LearningDocument
    from apps.questions.models import Question
    from apps.users.models import IrregularSubjectEnrollment, TeachingAssignment

    subject_ids = [s.pk for s in subjects]
    by_id = {s.pk: s for s in subjects}
    for subject in subjects:
        subject.faculty_count = 0
        subject.faculty_names = []
        subject.student_count = 0
        subject.question_count = 0
        subject.material_count = 0
    if not subject_ids:
        return

    faculty_rows = (
        TeachingAssignment.objects.filter(subject_id__in=subject_ids)
        .select_related("professor")
        .order_by("professor__first_name", "professor__last_name")
    )
    faculty_seen: dict[int, set[int]] = {s.pk: set() for s in subjects}
    for row in faculty_rows:
        if row.professor_id in faculty_seen[row.subject_id]:
            continue
        faculty_seen[row.subject_id].add(row.professor_id)
        name = row.professor.get_full_name() or row.professor.email
        by_id[row.subject_id].faculty_names.append(name)
    for subject in subjects:
        subject.faculty_count = len(faculty_seen[subject.pk])

    question_rows = (
        Question.objects.filter(topic__subject_id__in=subject_ids)
        .values("topic__subject_id")
        .annotate(total=Count("id"))
    )
    for row in question_rows:
        by_id[row["topic__subject_id"]].question_count = row["total"]

    material_rows = (
        LearningDocument.objects.filter(subject_id__in=subject_ids, is_archived=False)
        .values("subject_id")
        .annotate(total=Count("id"))
    )
    for row in material_rows:
        by_id[row["subject_id"]].material_count = row["total"]

    combo_to_subjects: dict[tuple[int, int], list] = {}
    for subject in subjects:
        combo_to_subjects.setdefault(
            (subject.program_id, subject.year_level_id), []
        ).append(subject)
    regular_rows = (
        User.objects.filter(
            role=User.Role.STUDENT,
            section__program_id__in=[s.program_id for s in subjects],
            year_level_id__in=[s.year_level_id for s in subjects],
        )
        .values("section__program_id", "year_level_id")
        .annotate(total=Count("id"))
    )
    for row in regular_rows:
        for subject in combo_to_subjects.get(
            (row["section__program_id"], row["year_level_id"]), []
        ):
            subject.student_count += row["total"]
    irregular_rows = (
        IrregularSubjectEnrollment.objects.filter(
            subject_id__in=subject_ids, status="enrolled"
        )
        .values("subject_id")
        .annotate(total=Count("student_id", distinct=True))
    )
    for row in irregular_rows:
        by_id[row["subject_id"]].student_count += row["total"]

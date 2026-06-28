"""Program section lookup and validation helpers."""

from django.core.exceptions import ValidationError

from apps.users.models import AcademicYear, Program, ProgramSection, User


def get_current_academic_year() -> AcademicYear | None:
    """Return the active academic year, creating a default if none exists."""
    current = AcademicYear.get_current()
    if current:
        return current
    default_label = "2025-2026"
    year, _created = AcademicYear.objects.get_or_create(
        label=default_label,
        defaults={"is_current": True},
    )
    if not year.is_current:
        year.is_current = True
        year.save(update_fields=["is_current"])
    return year


def sections_for_student(
    program_slug: str,
    year_level_id: int | None,
    *,
    academic_year: AcademicYear | None = None,
    exclude_user: User | None = None,
) -> ProgramSection.objects.__class__:
    """Active sections matching program + year level for the current academic year."""
    program = Program.for_home_degree(program_slug)
    if not program or not year_level_id:
        return ProgramSection.objects.none()

    year = academic_year or get_current_academic_year()
    if not year:
        return ProgramSection.objects.none()

    return (
        ProgramSection.queryset_with_counts()
        .filter(
            program=program,
            year_level_id=year_level_id,
            academic_year=year,
            is_active=True,
        )
        .select_related("program", "year_level", "academic_year")
        .order_by("label")
    )


def validate_section_capacity(
    section: ProgramSection,
    *,
    exclude_user: User | None = None,
) -> None:
    """Raise ValidationError if the section is full (excluding the given user)."""
    count = section.students.filter(role=User.Role.STUDENT)
    if exclude_user and exclude_user.pk:
        count = count.exclude(pk=exclude_user.pk)
    enrolled = count.count()
    if enrolled >= section.max_students:
        raise ValidationError("This section is full. Choose another section.")


def section_matches_student(
    section: ProgramSection,
    program_slug: str,
    year_level_id: int | None,
) -> bool:
    """Return True when the section aligns with the student's program and year."""
    program = Program.for_home_degree(program_slug)
    if not program or not year_level_id:
        return False
    return (
        section.program_id == program.pk
        and section.year_level_id == year_level_id
        and section.is_active
    )

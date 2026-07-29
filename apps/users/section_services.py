"""Program section lookup and validation helpers."""

from __future__ import annotations

import re

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


def parse_section_label(raw: str) -> str:
    """Normalize typed section text to a ProgramSection.label (e.g. 1M, 2M).

    Accepts: ``1M``, ``2-1M``, ``BSE 2-1M``, ``bse2-1m``.
    """
    text = (raw or "").strip().upper()
    text = re.sub(r"\s+", " ", text)
    if not text:
        raise ValidationError("Section is required.")

    text = re.sub(r"^BSE[\s\-]?", "", text)
    # year-block e.g. 2-1M or 2-1
    match = re.fullmatch(r"(\d+)\s*[-–]\s*([0-9A-Z]+)", text)
    if match:
        return match.group(2)

    # bare block e.g. 1M, 2M, 3
    if re.fullmatch(r"[0-9A-Z]{1,10}", text):
        return text

    raise ValidationError(
        "Enter a section like 1M, 2-1M, or BSE 2-1M."
    )


def get_or_create_student_section(
    year_level,
    label: str,
    *,
    exclude_user: User | None = None,
) -> ProgramSection:
    """Ensure a BSED Math ProgramSection exists for year + block label."""
    program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
    if program is None:
        raise ValidationError("BSEd Mathematics program is not configured.")
    academic_year = get_current_academic_year()
    if academic_year is None:
        raise ValidationError("No academic year is configured.")

    section, _ = ProgramSection.objects.get_or_create(
        program=program,
        year_level=year_level,
        label=label,
        academic_year=academic_year,
        defaults={"max_students": 40, "is_active": True},
    )
    if not section.is_active:
        section.is_active = True
        section.save(update_fields=["is_active"])
    validate_section_capacity(section, exclude_user=exclude_user)
    return section


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

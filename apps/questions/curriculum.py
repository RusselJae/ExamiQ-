"""Curriculum lookup helpers for cascading dropdowns and filtering."""

from apps.questions.models import Subject, Topic, YearLevel
from apps.users.models import Program


def get_year_levels():
    return YearLevel.objects.all()


def get_subjects_for_program(
    program_id: int | None,
    year_level_id: int | None = None,
    *,
    exclude_placeholder: bool = True,
    strict_year: bool = True,
):
    qs = Subject.objects.select_related("program", "year_level").filter(program_id=program_id)
    if exclude_placeholder:
        qs = qs.exclude(code__startswith="GEN-")
    if year_level_id and strict_year:
        qs = qs.filter(year_level_id=year_level_id)
    return qs.order_by("year_level__order", "semester", "code")


def get_subjects_for_professor(program_id: int | None, year_level_id: int | None = None):
    """Professor subject list: filter by year when possible, else all catalog subjects."""
    qs = get_subjects_for_program(program_id, year_level_id, strict_year=True)
    if year_level_id and not qs.exists():
        qs = get_subjects_for_program(program_id, exclude_placeholder=True, strict_year=False)
    return qs


def get_topics_for_subject(subject_id: int | None):
    if not subject_id:
        return Topic.objects.none()
    return Topic.objects.filter(subject_id=subject_id, parent__isnull=True).order_by("name")


def topics_for_program(program_id: int | None):
    if not program_id:
        return Topic.objects.none()
    return Topic.objects.filter(subject__program_id=program_id).select_related("subject").order_by(
        "subject__code", "name"
    )


def subject_queryset_for_student(user):
    program = user.home_program
    if not program:
        return Subject.objects.none()
    qs = Subject.objects.filter(program=program).exclude(code__startswith="GEN-")
    qs = qs.select_related("year_level")
    if user.year_level_id:
        qs = qs.filter(year_level_id=user.year_level_id)
    return qs.order_by("year_level__order", "semester", "code")


def program_from_slug(slug: str) -> Program | None:
    if not slug:
        return None
    return Program.objects.filter(slug=slug).first()

"""Template context processors for global navigation."""

from apps.users.assignment_services import (
    get_professor_course_queryset,
    get_professor_section_nav,
)
from apps.users.models import Course, ProgramSection, User
from apps.users.notification_services import unread_notification_count


def navigation_context(request):
    """Provide professor sidebar course list and active course context."""
    context = {
        "professor_courses": [],
        "professor_section_nav": [],
        "sidebar_course": None,
        "sidebar_section": None,
        "sidebar_section_label": "",
        "sidebar_subject": None,
        "summary_courses": [],
        "unread_notification_count": 0,
        "pending_concern_count": 0,
    }
    user = request.user
    if not user.is_authenticated:
        return context

    context["unread_notification_count"] = unread_notification_count(user)

    if user.role != User.Role.PROFESSOR:
        return context

    context["professor_courses"] = list(
        get_professor_course_queryset(user)
        .select_related("program")
        .order_by("code", "section", "-academic_year", "term")
    )
    context["professor_section_nav"] = get_professor_section_nav(user)
    context["summary_courses"] = [
        {
            "pk": course.pk,
            "code": course.code,
            "label": f"{course.code} — {(course.section or '').strip() or course.name}",
        }
        for course in context["professor_courses"]
    ]

    match = getattr(request, "resolver_match", None)
    if not match or match.namespace != "analytics_professor":
        return context

    url_name = match.url_name or ""

    if url_name.startswith("section_"):
        section_id = match.kwargs.get("pk") or match.kwargs.get("section_pk")
        if section_id:
            try:
                section = ProgramSection.objects.select_related(
                    "program", "year_level", "academic_year"
                ).get(pk=section_id)
                context["sidebar_section"] = section
                context["sidebar_section_label"] = section.display_label
                from apps.analytics.concern_services import pending_concern_count_for_section

                context["pending_concern_count"] = pending_concern_count_for_section(
                    section
                )
            except ProgramSection.DoesNotExist:
                pass
        return context

    course_id = match.kwargs.get("course_pk") or match.kwargs.get("pk")
    # Subject analytics URLs still resolve a catalog course for sidebar tools
    if url_name in {"subject_detail", "subject_roster"}:
        from apps.questions.models import Subject
        from apps.users.assignment_services import get_or_create_catalog_course

        subject_id = match.kwargs.get("pk") or match.kwargs.get("subject_pk")
        if subject_id:
            try:
                subject = Subject.objects.select_related("program", "year_level").get(
                    pk=subject_id
                )
                context["sidebar_subject"] = subject
                context["sidebar_course"] = get_or_create_catalog_course(user, subject)
                context["sidebar_section_label"] = f"{subject.code} Catalog"
            except Subject.DoesNotExist:
                pass
        return context

    if course_id:
        try:
            course = Course.objects.select_related("program").get(
                pk=course_id,
                professor=user,
            )
            context["sidebar_course"] = course
            if (course.section or "").strip() == "Catalog":
                context["sidebar_section_label"] = f"{course.code} Catalog"
                from apps.questions.models import Subject

                context["sidebar_subject"] = Subject.objects.filter(
                    code=course.code, program=course.program
                ).first()
            else:
                context["sidebar_section_label"] = (
                    (course.section or "").strip() or course.code
                )
        except Course.DoesNotExist:
            pass

    return context

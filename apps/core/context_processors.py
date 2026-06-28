"""Template context processors for global navigation."""

from apps.analytics.services import pending_question_review_count
from apps.users.assignment_services import get_professor_course_queryset
from apps.users.models import Course, User
from apps.users.notification_services import unread_notification_count


def navigation_context(request):
    """Provide professor sidebar course list and active course context."""
    context = {
        "professor_courses": [],
        "sidebar_course": None,
        "pending_question_count": 0,
        "summary_courses": [],
        "unread_notification_count": 0,
    }
    user = request.user
    if not user.is_authenticated:
        return context

    context["unread_notification_count"] = unread_notification_count(user)

    if user.role == User.Role.CHAIRPERSON:
        context["pending_question_count"] = pending_question_review_count(user)

    if user.role != User.Role.PROFESSOR:
        return context

    context["professor_courses"] = list(
        get_professor_course_queryset(user)
        .select_related("program")
        .order_by("code", "section", "-academic_year", "term")
    )
    context["summary_courses"] = [
        {
            "pk": course.pk,
            "code": course.code,
            "label": (
                f"{course.code} · Sec {course.section} · {course.term} {course.academic_year}"
                if course.section
                else f"{course.code} · {course.term} {course.academic_year}"
            ),
        }
        for course in context["professor_courses"]
    ]

    match = getattr(request, "resolver_match", None)
    if not match or match.namespace != "analytics_professor":
        return context

    course_id = match.kwargs.get("course_pk") or match.kwargs.get("pk")
    if course_id:
        try:
            context["sidebar_course"] = Course.objects.select_related("program").get(
                pk=course_id,
                professor=user,
            )
        except Course.DoesNotExist:
            pass

    return context

"""Template context processors for global navigation."""

from apps.analytics.services import pending_question_review_count
from apps.users.models import Course, User


def navigation_context(request):
    """Provide professor sidebar course list and active course context."""
    context = {
        "professor_courses": [],
        "sidebar_course": None,
        "pending_question_count": 0,
        "summary_courses": [],
    }
    user = request.user
    if not user.is_authenticated:
        return context

    if user.role == User.Role.CHAIRPERSON:
        context["pending_question_count"] = pending_question_review_count(user)

    if user.role != User.Role.PROFESSOR:
        return context

    context["professor_courses"] = list(
        Course.objects.filter(professor=user).select_related("program").order_by("code")
    )
    context["summary_courses"] = [
        {
            "pk": course.pk,
            "code": course.code,
            "label": f"{course.code} · {course.term} {course.academic_year}",
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

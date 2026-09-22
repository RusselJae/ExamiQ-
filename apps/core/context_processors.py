"""Template context processors for global navigation."""

from django.urls import reverse

from apps.users.assignment_services import get_professor_course_queryset
from apps.users.models import Course, User
from apps.users.notification_services import (
    recent_notifications,
    unread_notification_count,
)


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
        "recent_notifications": [],
        "pending_concern_count": 0,
        "chat_inbox_url": "",
        "chat_concerns_url": "",
        "chat_conversations_url": "",
        "chat_note_url_base": "",
        "chat_message_url": "",
        "chat_concern_url_template": "",
        "faculty_chat_conversations_url": "",
        "faculty_chat_message_url": "",
        "faculty_chat_note_url_base": "",
        "show_chat_modal": False,
        "show_ai_tutor_modal": False,
        "tutor_url_templates": {},
        "tutor_default_session_id": None,
        "chat_self_avatar_url": "",
        "chat_self_initials": "",
        "chat_self_name": "",
    }
    user = request.user
    if not user.is_authenticated:
        return context

    context["unread_notification_count"] = unread_notification_count(user)
    context["recent_notifications"] = recent_notifications(user, limit=8)
    context["chat_self_name"] = user.get_full_name() or user.email
    context["chat_self_initials"] = user.initials
    if user.profile_photo:
        try:
            context["chat_self_avatar_url"] = user.profile_photo.url
        except ValueError:
            context["chat_self_avatar_url"] = ""

    if user.role == User.Role.STUDENT:
        from apps.analytics.chat_services import pending_chat_count_for_student
        from apps.reviews.models import ReviewSession

        context["pending_concern_count"] = pending_chat_count_for_student(user)
        context["chat_inbox_url"] = reverse("analytics_student:chat_inbox")
        context["chat_conversations_url"] = reverse(
            "analytics_student:chat_conversations_api"
        )
        context["chat_concerns_url"] = context["chat_conversations_url"]
        context["chat_message_url"] = reverse("analytics_student:chat_message")
        context["show_chat_modal"] = True
        context["show_ai_tutor_modal"] = True
        context["tutor_url_templates"] = {
            "history": reverse("reviews:tutor_history", kwargs={"pk": 0}).replace(
                "/0/", "/{pk}/"
            ),
            "chat": reverse("reviews:tutor_chat", kwargs={"pk": 0}).replace(
                "/0/", "/{pk}/"
            ),
            "feedback": reverse(
                "reviews:session_generate_feedback", kwargs={"pk": 0}
            ).replace("/0/", "/{pk}/"),
            "concern": reverse(
                "analytics_student:upload_mistake_concern", kwargs={"answer_pk": 0}
            ).replace("/0/", "/{pk}/"),
        }
        latest = (
            ReviewSession.objects.filter(
                student=user,
                status=ReviewSession.Status.COMPLETED,
            )
            .order_by("-ended_at", "-pk")
            .values_list("pk", flat=True)
            .first()
        )
        context["tutor_default_session_id"] = latest
        return context

    if user.role != User.Role.PROFESSOR:
        return context

    from apps.analytics.chat_services import pending_chat_count_for_professor

    context["pending_concern_count"] = pending_chat_count_for_professor(user)
    context["chat_inbox_url"] = reverse("analytics_professor:chat_inbox")
    context["chat_conversations_url"] = reverse(
        "analytics_professor:chat_conversations_api"
    )
    context["chat_concerns_url"] = context["chat_conversations_url"]
    context["chat_note_url_base"] = reverse(
        "analytics_professor:chat_faculty_message", kwargs={"conversation_pk": 0}
    )
    context["faculty_chat_conversations_url"] = reverse(
        "analytics_professor:faculty_chat_conversations_api"
    )
    context["faculty_chat_message_url"] = reverse(
        "analytics_professor:faculty_chat_message_start"
    )
    context["faculty_chat_note_url_base"] = reverse(
        "analytics_professor:faculty_chat_message", kwargs={"conversation_pk": 0}
    )
    context["show_chat_modal"] = True

    context["professor_courses"] = list(
        get_professor_course_queryset(user)
        .select_related("program")
        .order_by("code", "section", "-academic_year", "term")
    )
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

    # Section URLs keep working if deep-linked; no sidebar section nav.
    if url_name.startswith("section_"):
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


"""Student–faculty chat (one thread per student)."""

from __future__ import annotations

import logging

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.analytics.models import StudentFacultyConversation, StudentFacultyMessage
from apps.users.assignment_services import (
    faculty_has_chat_scope,
    get_faculty_profile_section_ids,
    get_faculty_profile_subject_ids,
)
from apps.users.models import User
from apps.users.notification_services import create_notification

logger = logging.getLogger(__name__)


def get_or_create_conversation(student: User) -> StudentFacultyConversation:
    """Ensure the student has a single faculty chat thread."""
    conversation, _ = StudentFacultyConversation.objects.get_or_create(
        student=student,
    )
    return conversation


def conversation_has_messages(conversation: StudentFacultyConversation) -> bool:
    return conversation.messages.exists()


def latest_chat_message(
    conversation: StudentFacultyConversation,
) -> StudentFacultyMessage | None:
    return (
        conversation.messages.order_by("-created_at", "-pk")
        .select_related("author")
        .first()
    )


def chat_needs_faculty_reply(conversation: StudentFacultyConversation) -> bool:
    """Pending when the latest message is from the student."""
    latest = latest_chat_message(conversation)
    if latest:
        return latest.author_id == conversation.student_id
    return False


def chat_needs_student_attention(conversation: StudentFacultyConversation) -> bool:
    """True when the latest message is from faculty."""
    latest = latest_chat_message(conversation)
    if latest:
        return latest.author_id != conversation.student_id
    return False


def _professors_for_student(student: User) -> list[User]:
    """Faculty assigned to the student's section with chat scope configured."""
    student_section = getattr(student, "section", None)
    if student_section is None:
        return []

    professors = (
        User.objects.filter(
            role=User.Role.PROFESSOR,
            assigned_sections=student_section,
        )
        .distinct()
        .order_by("email")
    )
    return [prof for prof in professors if faculty_has_chat_scope(prof)]


def _professor_in_chat_scope(professor: User, student: User) -> bool:
    section_ids = get_faculty_profile_section_ids(professor)
    subject_ids = get_faculty_profile_subject_ids(professor)
    if not section_ids or not subject_ids:
        return False
    student_section_id = getattr(student, "section_id", None)
    return student_section_id in section_ids


def professor_can_access_conversation(
    professor: User, conversation: StudentFacultyConversation
) -> bool:
    if conversation.participating_faculty.filter(pk=professor.pk).exists():
        return True
    return _professor_in_chat_scope(professor, conversation.student)


def professor_chat_queryset(professor: User):
    """Conversations visible to faculty (scope or prior participation)."""
    section_ids = get_faculty_profile_section_ids(professor)
    subject_ids = get_faculty_profile_subject_ids(professor)
    scope_filter = Q()
    if section_ids and subject_ids:
        scope_filter = Q(student__section_id__in=section_ids)
    owned_filter = Q(participating_faculty=professor)
    if scope_filter:
        thread_filter = scope_filter | owned_filter
    else:
        thread_filter = owned_filter

    return (
        StudentFacultyConversation.objects.filter(thread_filter)
        .filter(messages__isnull=False)
        .select_related("student", "student__section")
        .prefetch_related("messages__author", "participating_faculty")
        .distinct()
        .order_by("-last_message_at", "-created_at")
    )


def student_chat_conversation(student: User) -> StudentFacultyConversation:
    return get_or_create_conversation(student)


def user_avatar_url(user: User | None) -> str:
    if not user or not getattr(user, "profile_photo", None):
        return ""
    try:
        return user.profile_photo.url
    except ValueError:
        return ""


def _message_image_url(message: StudentFacultyMessage) -> str:
    if not message.image:
        return ""
    try:
        return message.image.url
    except ValueError:
        return ""


def serialize_chat_message(message: StudentFacultyMessage) -> dict:
    author = message.author
    role = "student" if author.role == User.Role.STUDENT else "faculty"
    name = author.get_full_name() or author.email
    parts = (author.first_name or "", author.last_name or "")
    if parts[0] and parts[1]:
        initials = (parts[0][0] + parts[1][0]).upper()
    else:
        initials = (name[:2] or "?").upper()
    return {
        "id": message.pk,
        "author_role": role,
        "author_name": name,
        "author_initials": initials,
        "author_avatar_url": user_avatar_url(author),
        "body": message.body or "",
        "image_url": _message_image_url(message),
        "image_name": (
            (message.image.name.rsplit("/", 1)[-1] if message.image else "") or ""
        ),
        "created_at": message.created_at.isoformat() if message.created_at else "",
    }


def serialize_conversation(
    conversation: StudentFacultyConversation,
    *,
    viewer: User | None = None,
) -> dict:
    """JSON payload for the chat modal."""
    student = conversation.student
    name = student.get_full_name() or student.email
    if student.first_name and student.last_name:
        initials = (student.first_name[0] + student.last_name[0]).upper()
    else:
        initials = (name[:2] or "?").upper()

    messages = [
        serialize_chat_message(msg)
        for msg in StudentFacultyMessage.objects.filter(conversation=conversation)
        .select_related("author")
        .order_by("created_at", "pk")
    ]
    latest_msg = messages[-1] if messages else None
    latest_student = next(
        (m for m in reversed(messages) if m["author_role"] == "student"),
        None,
    )
    preview = ""
    if latest_msg:
        preview = (latest_msg.get("body") or "").strip()
        if not preview and latest_msg.get("image_url"):
            preview = "Sent an image"
    elif latest_student:
        preview = (latest_student.get("body") or "").strip()

    peer_name = "Faculty"
    peer_initials = "FA"
    peer_avatar_url = ""
    if viewer and viewer.role == User.Role.STUDENT:
        latest_faculty = next(
            (m for m in reversed(messages) if m["author_role"] == "faculty"),
            None,
        )
        if latest_faculty:
            peer_name = latest_faculty.get("author_name") or "Faculty"
            peer_initials = latest_faculty.get("author_initials") or "FA"
            peer_avatar_url = latest_faculty.get("author_avatar_url") or ""

    return {
        "conversation_id": conversation.pk,
        "student_id": student.pk,
        "student_name": name,
        "student_email": student.email,
        "student_initials": initials,
        "student_avatar_url": user_avatar_url(student),
        "peer_name": peer_name,
        "peer_initials": peer_initials,
        "peer_avatar_url": peer_avatar_url,
        "preview": preview,
        "last_message_at": (
            (latest_msg.get("created_at") if latest_msg else "")
            or (
                conversation.last_message_at.isoformat()
                if conversation.last_message_at
                else ""
            )
        ),
        "needs_faculty_reply": chat_needs_faculty_reply(conversation),
        "needs_student_attention": chat_needs_student_attention(conversation),
        "messages": messages,
    }


def post_chat_message(
    conversation: StudentFacultyConversation,
    author: User,
    *,
    body: str = "",
    image=None,
) -> StudentFacultyMessage:
    """Append a message to the student–faculty chat thread."""
    body = (body or "").strip()
    if not body and not image:
        raise ValueError("Message must include text or an image.")

    message = StudentFacultyMessage.objects.create(
        conversation=conversation,
        author=author,
        body=body,
        image=image,
    )
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["last_message_at"])

    if author.role == User.Role.STUDENT:
        for professor in _professors_for_student(conversation.student):
            conversation.participating_faculty.add(professor)
        _notify_professors_of_student_message(conversation, message)
    elif author.role == User.Role.PROFESSOR:
        conversation.participating_faculty.add(author)
        _notify_student_of_faculty_reply(conversation, message)

    return message


def mark_chat_notifications_read(
    user: User,
    *,
    conversation_id: int | None = None,
    student_id: int | None = None,
) -> None:
    """Mark notifications tied to a chat conversation as read."""
    from apps.users.notification_services import mark_notifications_read

    qs = user.notifications.filter(read_at__isnull=True)
    if conversation_id is not None:
        qs = qs.filter(link__contains=f"conversation_id={conversation_id}")
    elif student_id is not None:
        qs = qs.filter(link__contains=f"student_id={student_id}")
    else:
        return
    ids = list(qs.values_list("pk", flat=True))
    if ids:
        mark_notifications_read(user, ids)


def _chat_link_for_student(conversation: StudentFacultyConversation) -> str:
    return (
        reverse("analytics_student:dashboard")
        + f"?open_chat=1&conversation_id={conversation.pk}"
    )


def _chat_link_for_professor(
    conversation: StudentFacultyConversation, professor: User
) -> str:
    return (
        reverse("analytics_professor:overview")
        + f"?open_chat=1&student_id={conversation.student_id}"
        + f"&conversation_id={conversation.pk}"
    )


def _notify_professors_of_student_message(
    conversation: StudentFacultyConversation,
    message: StudentFacultyMessage,
) -> None:
    professors = _professors_for_student(conversation.student)
    if not professors:
        logger.warning(
            "No professors to notify for chat message=%s conversation=%s student=%s",
            message.pk,
            conversation.pk,
            conversation.student_id,
        )
        return

    student_name = conversation.student.get_full_name() or conversation.student.email
    text = f"{student_name} sent you a message"
    for professor in professors:
        create_notification(
            professor,
            text,
            link=_chat_link_for_professor(conversation, professor),
        )


def _notify_student_of_faculty_reply(
    conversation: StudentFacultyConversation,
    message: StudentFacultyMessage,
) -> None:
    create_notification(
        conversation.student,
        "Faculty replied to your message",
        link=_chat_link_for_student(conversation),
    )


def pending_chat_count_for_student(student: User) -> int:
    conversation = (
        StudentFacultyConversation.objects.filter(student=student)
        .prefetch_related("messages__author")
        .first()
    )
    if not conversation:
        return 0
    return 1 if chat_needs_student_attention(conversation) else 0


def pending_chat_count_for_professor(professor: User) -> int:
    qs = professor_chat_queryset(professor)
    return sum(1 for conv in qs if chat_needs_faculty_reply(conv))

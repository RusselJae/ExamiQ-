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
from apps.users.models import StudentFacultyAssignment, TeachingAssignment, User
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


def professors_for_student_courses(student: User) -> list[User]:
    """Faculty currently teaching the student's courses.

    Combines the section's current TeachingAssignment rows, the student's
    explicit per-subject faculty assignments, and the legacy profile scope so
    existing chats keep working while the coordinator's teaching load is the
    primary source.
    """
    from apps.users.section_services import get_current_academic_year

    professor_ids = {prof.pk for prof in _professors_for_student(student)}
    current_year = get_current_academic_year()

    if student.section_id:
        teaching = TeachingAssignment.objects.filter(
            program_section_id=student.section_id,
        )
        if current_year is not None:
            teaching = teaching.filter(term__academic_year=current_year)
        professor_ids |= set(teaching.values_list("professor_id", flat=True))

    assigned = StudentFacultyAssignment.objects.filter(student=student)
    if current_year is not None:
        assigned = assigned.filter(academic_year=current_year)
    professor_ids |= set(assigned.values_list("faculty_id", flat=True))

    if not professor_ids:
        return []
    return list(
        User.objects.filter(
            pk__in=professor_ids,
            role=User.Role.PROFESSOR,
            is_active=True,
            is_archived=False,
        ).order_by("first_name", "last_name", "email")
    )


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
        "author_id": author.pk,
        "author_role": role,
        "author_name": name,
        "author_initials": initials,
        "author_avatar_url": user_avatar_url(author),
        "recipient_id": message.recipient_id,
        "recipient_name": (
            message.recipient.get_full_name() or message.recipient.email
            if message.recipient
            else ""
        ),
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
    faculty_filter: User | None = None,
) -> dict:
    """JSON payload for the chat modal.

    ``faculty_filter`` produces the student-side contact thread for one
    faculty member, including legacy broadcast messages and messages addressed
    to that faculty member.
    """
    student = conversation.student
    name = student.get_full_name() or student.email
    if student.first_name and student.last_name:
        initials = (student.first_name[0] + student.last_name[0]).upper()
    else:
        initials = (name[:2] or "?").upper()

    messages_qs = StudentFacultyMessage.objects.filter(
        conversation=conversation
    ).select_related("author", "recipient")
    if faculty_filter is not None:
        messages_qs = messages_qs.filter(
            Q(author__role=User.Role.STUDENT, recipient__isnull=True)
            | Q(author__role=User.Role.STUDENT, recipient=faculty_filter)
            | Q(author=faculty_filter)
        )
    messages = [
        serialize_chat_message(msg) for msg in messages_qs.order_by("created_at", "pk")
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
    elif faculty_filter is not None:
        preview = "Start a conversation"

    peer_name = "Faculty"
    peer_initials = "FA"
    peer_avatar_url = ""
    peer_email = ""
    peer_id = None
    if faculty_filter is not None:
        peer_id = faculty_filter.pk
        peer_name = faculty_filter.get_full_name() or faculty_filter.email
        if faculty_filter.first_name and faculty_filter.last_name:
            peer_initials = (
                faculty_filter.first_name[0] + faculty_filter.last_name[0]
            ).upper()
        else:
            peer_initials = (peer_name[:2] or "FA").upper()
        peer_avatar_url = user_avatar_url(faculty_filter)
        peer_email = faculty_filter.email
    elif viewer and viewer.role == User.Role.STUDENT:
        latest_faculty = next(
            (m for m in reversed(messages) if m["author_role"] == "faculty"),
            None,
        )
        if latest_faculty:
            peer_name = latest_faculty.get("author_name") or "Faculty"
            peer_initials = latest_faculty.get("author_initials") or "FA"
            peer_avatar_url = latest_faculty.get("author_avatar_url") or ""

    if faculty_filter is not None:
        latest_role = messages[-1]["author_role"] if messages else None
        needs_faculty_reply = latest_role == "student"
        needs_student_attention = latest_role == "faculty"
    else:
        needs_faculty_reply = chat_needs_faculty_reply(conversation)
        needs_student_attention = chat_needs_student_attention(conversation)

    return {
        "conversation_id": conversation.pk,
        "thread_type": "student",
        "student_id": student.pk,
        "student_name": name,
        "student_email": student.email,
        "student_initials": initials,
        "student_avatar_url": user_avatar_url(student),
        "peer_id": peer_id,
        "peer_name": peer_name,
        "peer_email": peer_email,
        "peer_initials": peer_initials,
        "peer_avatar_url": peer_avatar_url,
        "preview": preview,
        "last_message_at": (
            (latest_msg.get("created_at") if latest_msg else "")
            or (
                conversation.last_message_at.isoformat()
                if conversation.last_message_at and faculty_filter is None
                else ""
            )
        ),
        "needs_faculty_reply": needs_faculty_reply,
        "needs_student_attention": needs_student_attention,
        "messages": messages,
    }


def serialize_student_faculty_thread(
    conversation: StudentFacultyConversation,
    faculty: User,
    *,
    viewer: User,
) -> dict:
    """Student-side virtual contact thread for one faculty member."""
    item = serialize_conversation(conversation, viewer=viewer, faculty_filter=faculty)
    # A student's sidebar keys contact threads by peer id; they all share the
    # single database conversation, so the conversation id must not collide.
    item["conversation_id"] = None
    item["faculty_id"] = faculty.pk
    item["peer_id"] = faculty.pk
    return item


def student_chat_inbox_payload(
    student: User,
    *,
    faculty_id: str | None = None,
) -> dict:
    """Build the student's faculty contact list for the Chat modal."""
    conversation = get_or_create_conversation(student)
    contacts = professors_for_student_courses(student)

    if not contacts:
        conversation.refresh_from_db()
        return {
            "items": [serialize_conversation(conversation, viewer=student)],
            "active_conversation_id": conversation.pk,
            "active_peer_id": None,
        }

    items = [
        serialize_student_faculty_thread(conversation, faculty, viewer=student)
        for faculty in contacts
    ]
    with_messages = sorted(
        (item for item in items if item.get("last_message_at")),
        key=lambda item: item["last_message_at"],
        reverse=True,
    )
    without_messages = sorted(
        (item for item in items if not item.get("last_message_at")),
        key=lambda item: (item.get("peer_name") or "").lower(),
    )
    items = with_messages + without_messages

    active_peer_id = None
    if faculty_id and str(faculty_id).isdigit():
        requested = int(faculty_id)
        if any(item.get("peer_id") == requested for item in items):
            active_peer_id = requested
    if active_peer_id is None and items:
        active_peer_id = items[0].get("peer_id")

    return {
        "items": items,
        "active_conversation_id": None,
        "active_peer_id": active_peer_id,
    }


def post_chat_message(
    conversation: StudentFacultyConversation,
    author: User,
    *,
    body: str = "",
    image=None,
    recipient: User | None = None,
) -> StudentFacultyMessage:
    """Append a message to the student–faculty chat thread."""
    body = (body or "").strip()
    if not body and not image:
        raise ValueError("Message must include text or an image.")
    if recipient is not None and recipient.role != User.Role.PROFESSOR:
        raise ValueError("Messages can only target a faculty member.")

    message = StudentFacultyMessage.objects.create(
        conversation=conversation,
        author=author,
        recipient=recipient,
        body=body,
        image=image,
    )
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["last_message_at"])

    if author.role == User.Role.STUDENT:
        professors = (
            [recipient]
            if recipient is not None
            else professors_for_student_courses(conversation.student)
        )
        for professor in professors:
            conversation.participating_faculty.add(professor)
        _notify_professors_of_student_message(
            conversation, message, recipient=recipient
        )
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


def _chat_link_for_student(
    conversation: StudentFacultyConversation,
    *,
    faculty_id: int | None = None,
) -> str:
    link = (
        reverse("analytics_student:dashboard")
        + f"?open_chat=1&conversation_id={conversation.pk}"
    )
    if faculty_id is not None:
        link += f"&faculty_id={faculty_id}"
    return link


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
    *,
    recipient: User | None = None,
) -> None:
    professors = (
        [recipient]
        if recipient is not None
        else professors_for_student_courses(conversation.student)
    )
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
        if professor is None:
            continue
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
        link=_chat_link_for_student(
            conversation,
            faculty_id=message.author_id,
        ),
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

"""Student–faculty concern thread helpers and notifications."""

from __future__ import annotations

import logging

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.analytics.models import MistakeConcernMessage, MistakeRecord
from apps.users.assignment_services import get_or_create_catalog_course
from apps.users.models import Course, User
from apps.users.notification_services import create_notification

logger = logging.getLogger(__name__)


def concern_has_activity(record: MistakeRecord) -> bool:
    """True when the mistake has thread messages or legacy concern fields."""
    if record.concern_messages.exists():
        return True
    if (record.student_note or "").strip():
        return True
    if record.student_image:
        return True
    if (record.faculty_note or "").strip():
        return True
    return False


def concern_thread_for(record: MistakeRecord):
    """Ordered concern messages for a mistake record."""
    return record.concern_messages.select_related("author").order_by("created_at")


def latest_concern_message(record: MistakeRecord) -> MistakeConcernMessage | None:
    return record.concern_messages.order_by("-created_at").select_related("author").first()


def concern_needs_faculty_reply(record: MistakeRecord) -> bool:
    """Pending when the latest message is from the student."""
    latest = latest_concern_message(record)
    if latest:
        return latest.author_id == record.student_id
    return bool((record.student_note or "").strip() or record.student_image)


def concern_needs_student_attention(record: MistakeRecord) -> bool:
    """True when the latest message is from faculty (student should check Chat)."""
    latest = latest_concern_message(record)
    if latest:
        return latest.author_id != record.student_id
    return bool((record.faculty_note or "").strip())


def concern_has_faculty_reply(record: MistakeRecord) -> bool:
    latest = latest_concern_message(record)
    if latest:
        return latest.author_id != record.student_id
    return bool((record.faculty_note or "").strip())


def _concern_activity_filter() -> Q:
    return (
        Q(concern_messages__isnull=False)
        | Q(student_note__gt="")
        | (Q(student_image__isnull=False) & ~Q(student_image=""))
        | Q(faculty_note__gt="")
    )


def concern_queryset_with_messages(queryset):
    """Prefetch thread messages for concern list/API payloads."""
    return queryset.prefetch_related(
        "concern_messages__author",
    ).distinct()


def post_concern_message(
    mistake_record: MistakeRecord,
    author: User,
    *,
    body: str = "",
    image=None,
) -> MistakeConcernMessage:
    """Append a message to a concern thread."""
    body = (body or "").strip()
    if not body and not image:
        raise ValueError("Message must include text or an image.")

    message = MistakeConcernMessage.objects.create(
        mistake_record=mistake_record,
        author=author,
        body=body,
        image=image,
    )

    if author.role == User.Role.STUDENT:
        update_fields: list[str] = []
        if body:
            mistake_record.student_note = body
            update_fields.append("student_note")
        if image:
            mistake_record.student_image = image
            update_fields.append("student_image")
        if update_fields:
            mistake_record.save(update_fields=update_fields)
        for professor in _professors_for_mistake(mistake_record):
            mistake_record.concern_faculty.add(professor)
        _notify_professors_of_student_message(mistake_record, message)
    elif author.role == User.Role.PROFESSOR:
        update_fields = ["faculty_noted_at"]
        mistake_record.faculty_noted_at = timezone.now()
        if body:
            mistake_record.faculty_note = body
            update_fields.append("faculty_note")
        mistake_record.save(update_fields=update_fields)
        mistake_record.concern_faculty.add(author)
        _notify_student_of_faculty_reply(mistake_record, message)

    return message


def mark_faculty_viewed(mistake_record: MistakeRecord) -> None:
    now = timezone.now()
    if mistake_record.faculty_viewed_at != now:
        mistake_record.faculty_viewed_at = now
        mistake_record.save(update_fields=["faculty_viewed_at"])


def mark_concern_notifications_read(
    user: User,
    mistake_record_id: int | None = None,
    *,
    answer_id: int | None = None,
) -> None:
    """Mark notifications tied to a mistake concern as read."""
    from apps.users.notification_services import mark_notifications_read

    qs = user.notifications.filter(read_at__isnull=True)
    if mistake_record_id is not None:
        qs = qs.filter(link__contains=f"mistake_id={mistake_record_id}")
    elif answer_id is not None:
        qs = qs.filter(link__contains=f"answer_id={answer_id}")
    else:
        return
    ids = list(qs.values_list("pk", flat=True))
    if ids:
        mark_notifications_read(user, ids)


def _message_image_url(message: MistakeConcernMessage) -> str:
    if not message.image:
        return ""
    try:
        return message.image.url
    except ValueError:
        return ""


def user_avatar_url(user: User | None) -> str:
    if not user or not getattr(user, "profile_photo", None):
        return ""
    try:
        return user.profile_photo.url
    except ValueError:
        return ""


def serialize_concern_message(message: MistakeConcernMessage) -> dict:
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


def serialize_concern_thread(record: MistakeRecord) -> list[dict]:
    messages = list(concern_thread_for(record))
    if messages:
        return [serialize_concern_message(msg) for msg in messages]

    legacy: list[dict] = []
    if (record.student_note or "").strip() or record.student_image:
        image_url = ""
        if record.student_image:
            try:
                image_url = record.student_image.url
            except ValueError:
                image_url = ""
        legacy.append(
            {
                "id": None,
                "author_role": "student",
                "author_name": record.student.get_full_name() or record.student.email,
                "author_initials": (
                    (
                        (record.student.first_name or "")[:1]
                        + (record.student.last_name or "")[:1]
                    ).upper()
                    or (record.student.email or "?")[:2].upper()
                ),
                "author_avatar_url": user_avatar_url(record.student),
                "body": record.student_note or "",
                "image_url": image_url,
                "image_name": "",
                "created_at": record.occurred_at.isoformat() if record.occurred_at else "",
            }
        )
    if (record.faculty_note or "").strip():
        legacy.append(
            {
                "id": None,
                "author_role": "faculty",
                "author_name": "Faculty",
                "author_initials": "FA",
                "author_avatar_url": "",
                "body": record.faculty_note or "",
                "image_url": "",
                "image_name": "",
                "created_at": (
                    record.faculty_noted_at.isoformat() if record.faculty_noted_at else ""
                ),
            }
        )
    return legacy


def _professors_for_mistake(record: MistakeRecord) -> list[User]:
    """Faculty whose profile sections+subjects cover this student's mistake.

    Option B: faculty must have both sections and subjects set. No Catalog fallback.
    """
    subject = getattr(getattr(record.question, "topic", None), "subject", None)
    student_section = getattr(record.student, "section", None)
    if subject is None or student_section is None:
        return []

    return list(
        User.objects.filter(
            role=User.Role.PROFESSOR,
            assigned_sections=student_section,
            assigned_subjects=subject,
        )
        .distinct()
        .order_by("email")
    )


def _feedback_link_for_professor(record: MistakeRecord, professor: User) -> str:
    """Deep-link into overview with Chat modal open."""
    return (
        reverse("analytics_professor:overview")
        + f"?open_chat=1&student_id={record.student_id}"
    )


def _section_feedback_link(record: MistakeRecord) -> str:
    return (
        reverse("analytics_professor:overview")
        + f"?open_chat=1&student_id={record.student_id}"
    )


def _notify_professors_of_student_message(
    record: MistakeRecord,
    message: MistakeConcernMessage,
) -> None:
    professors = _professors_for_mistake(record)
    if not professors:
        subject = getattr(getattr(record.question, "topic", None), "subject", None)
        logger.warning(
            "No professors to notify for concern message=%s mistake=%s subject=%s student=%s",
            message.pk,
            record.pk,
            getattr(subject, "code", None),
            record.student_id,
        )
        return

    student_name = record.student.get_full_name() or record.student.email
    text = f"{student_name} asked about Q{record.question_id}"
    section_link = _section_feedback_link(record)
    for professor in professors:
        link = _feedback_link_for_professor(record, professor)
        if not link and section_link:
            link = section_link
        create_notification(professor, text, link=link)


def _notify_student_of_faculty_reply(
    record: MistakeRecord,
    message: MistakeConcernMessage,
) -> None:
    topic_name = record.topic.name
    link = reverse("analytics_student:dashboard") + "?open_chat=1"
    create_notification(
        record.student,
        f"Faculty replied to your question on {topic_name}",
        link=link,
    )


def pending_concern_count_for_course(course: Course) -> int:
    """Conversations for students in this course scope needing faculty reply."""
    from apps.analytics.chat_services import chat_needs_faculty_reply
    from apps.analytics.models import StudentFacultyConversation
    from apps.questions.models import Subject

    subject = Subject.objects.filter(code=course.code, program=course.program).first()
    if not subject:
        return 0
    qs = (
        StudentFacultyConversation.objects.filter(
            messages__isnull=False,
            student__mistake_records__question__topic__subject=subject,
        )
        .distinct()
        .prefetch_related("messages__author")
    )
    return sum(1 for conv in qs if chat_needs_faculty_reply(conv))


def pending_concern_count_for_section(section) -> int:
    from apps.analytics.chat_services import chat_needs_faculty_reply
    from apps.analytics.models import StudentFacultyConversation

    qs = (
        StudentFacultyConversation.objects.filter(
            student__section=section,
            messages__isnull=False,
        )
        .distinct()
        .prefetch_related("messages__author")
    )
    return sum(1 for conv in qs if chat_needs_faculty_reply(conv))


def professor_concern_queryset(professor: User):
    """Active concern threads for faculty profile scope plus persisted ownership."""
    from apps.users.assignment_services import (
        get_faculty_profile_section_ids,
        get_faculty_profile_subject_ids,
    )

    section_ids = get_faculty_profile_section_ids(professor)
    subject_ids = get_faculty_profile_subject_ids(professor)
    scope_filter = Q()
    if section_ids and subject_ids:
        scope_filter = Q(
            student__section_id__in=section_ids,
            question__topic__subject_id__in=subject_ids,
        )
    owned_filter = Q(concern_faculty=professor)
    if scope_filter:
        thread_filter = scope_filter | owned_filter
    else:
        thread_filter = owned_filter

    return concern_queryset_with_messages(
        MistakeRecord.objects.filter(thread_filter)
        .filter(_concern_activity_filter())
        .select_related(
            "student",
            "question",
            "topic",
            "answer",
            "answer__selected_choice",
            "question__topic",
            "question__topic__subject",
        )
        .prefetch_related("question__choices")
        .order_by("-occurred_at")
    )


def pending_concern_count_for_professor(professor: User) -> int:
    from apps.analytics.chat_services import pending_chat_count_for_professor

    return pending_chat_count_for_professor(professor)


def student_concern_queryset(student: User):
    """Active concern threads for a student."""
    return concern_queryset_with_messages(
        MistakeRecord.objects.filter(student=student)
        .filter(_concern_activity_filter())
        .select_related(
            "question",
            "topic",
            "answer",
            "question__topic",
            "question__topic__subject",
        )
        .prefetch_related("question__choices")
        .order_by("-occurred_at")
    )


def pending_concern_count_for_student(student: User) -> int:
    from apps.analytics.chat_services import pending_chat_count_for_student

    return pending_chat_count_for_student(student)


def _pending_concern_count(queryset):
    qs = concern_queryset_with_messages(
        queryset.filter(_concern_activity_filter())
    ).select_related("student")
    return sum(1 for record in qs if concern_needs_faculty_reply(record))

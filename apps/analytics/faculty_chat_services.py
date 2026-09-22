"""Faculty-to-faculty chat (one DM thread per professor pair)."""

from __future__ import annotations

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.analytics.chat_services import user_avatar_url
from apps.analytics.models import FacultyConversation, FacultyMessage
from apps.users.models import User
from apps.users.notification_services import create_notification


def _user_initials(user: User) -> str:
    name = user.get_full_name() or user.email
    if user.first_name and user.last_name:
        return (user.first_name[0] + user.last_name[0]).upper()
    return (name[:2] or "?").upper()


def _ordered_pair(a: User, b: User) -> tuple[User, User]:
    """Return (low_pk, high_pk) participants for the unique pair constraint."""
    if a.pk == b.pk:
        raise ValueError("Cannot start a faculty conversation with yourself.")
    if a.pk < b.pk:
        return a, b
    return b, a


def faculty_peers_queryset(viewer: User):
    """Active professors the viewer may message (same department when set)."""
    qs = User.objects.filter(
        role=User.Role.PROFESSOR,
        is_active=True,
    ).exclude(pk=viewer.pk)
    if viewer.department_id:
        qs = qs.filter(department_id=viewer.department_id)
    return qs.order_by("last_name", "first_name", "email")


def get_or_create_faculty_conversation(
    professor_a: User, professor_b: User
) -> FacultyConversation:
    """Ensure a DM thread exists between two professors."""
    low, high = _ordered_pair(professor_a, professor_b)
    conversation, _ = FacultyConversation.objects.get_or_create(
        participant_low=low,
        participant_high=high,
    )
    return conversation


def professor_can_access_faculty_conversation(
    professor: User, conversation: FacultyConversation
) -> bool:
    return professor.pk in (
        conversation.participant_low_id,
        conversation.participant_high_id,
    )


def professor_faculty_chat_queryset(professor: User):
    """Faculty DM threads visible to this professor (with at least one message)."""
    return (
        FacultyConversation.objects.filter(
            Q(participant_low=professor) | Q(participant_high=professor)
        )
        .filter(messages__isnull=False)
        .select_related("participant_low", "participant_high")
        .prefetch_related("messages__author")
        .distinct()
        .order_by("-last_message_at", "-created_at")
    )


def _message_image_url(message: FacultyMessage) -> str:
    if not message.image:
        return ""
    try:
        return message.image.url
    except ValueError:
        return ""


def serialize_faculty_message(message: FacultyMessage) -> dict:
    author = message.author
    name = author.get_full_name() or author.email
    return {
        "id": message.pk,
        "author_id": author.pk,
        "author_role": "faculty",
        "author_name": name,
        "author_initials": _user_initials(author),
        "author_avatar_url": user_avatar_url(author),
        "body": message.body or "",
        "image_url": _message_image_url(message),
        "image_name": (
            (message.image.name.rsplit("/", 1)[-1] if message.image else "") or ""
        ),
        "created_at": message.created_at.isoformat() if message.created_at else "",
    }


def serialize_faculty_conversation(
    conversation: FacultyConversation,
    *,
    viewer: User,
) -> dict:
    """JSON payload for the Chat modal faculty tab."""
    peer = conversation.other_participant(viewer)
    peer_name = peer.get_full_name() or peer.email
    peer_initials = _user_initials(peer)

    messages = [
        serialize_faculty_message(msg)
        for msg in FacultyMessage.objects.filter(conversation=conversation)
        .select_related("author")
        .order_by("created_at", "pk")
    ]
    latest_msg = messages[-1] if messages else None
    preview = ""
    if latest_msg:
        preview = (latest_msg.get("body") or "").strip()
        if not preview and latest_msg.get("image_url"):
            preview = "Sent an image"

    needs_reply = bool(latest_msg and latest_msg.get("author_id") != viewer.pk)

    return {
        "conversation_id": conversation.pk,
        "thread_type": "faculty",
        "peer_id": peer.pk,
        "peer_name": peer_name,
        "peer_initials": peer_initials,
        "peer_avatar_url": user_avatar_url(peer),
        "peer_email": peer.email,
        # Mirror peer into student_* so existing list rendering still works.
        "student_id": peer.pk,
        "student_name": peer_name,
        "student_email": peer.email,
        "student_initials": peer_initials,
        "student_avatar_url": user_avatar_url(peer),
        "preview": preview,
        "last_message_at": (
            (latest_msg.get("created_at") if latest_msg else "")
            or (
                conversation.last_message_at.isoformat()
                if conversation.last_message_at
                else ""
            )
        ),
        "needs_faculty_reply": needs_reply,
        "needs_student_attention": False,
        "messages": messages,
    }


def serialize_faculty_peer(peer: User) -> dict:
    """List row for a peer with no open conversation yet."""
    name = peer.get_full_name() or peer.email
    initials = _user_initials(peer)
    return {
        "conversation_id": None,
        "thread_type": "faculty",
        "peer_id": peer.pk,
        "peer_name": name,
        "peer_initials": initials,
        "peer_avatar_url": user_avatar_url(peer),
        "peer_email": peer.email,
        "student_id": peer.pk,
        "student_name": name,
        "student_email": peer.email,
        "student_initials": initials,
        "student_avatar_url": user_avatar_url(peer),
        "preview": "Start a conversation",
        "last_message_at": "",
        "needs_faculty_reply": False,
        "needs_student_attention": False,
        "messages": [],
    }


def faculty_inbox_payload(
    viewer: User, *, active_conversation_id: int | None = None
) -> dict:
    """Conversations plus peers without threads for the faculty tab."""
    conversations = list(professor_faculty_chat_queryset(viewer)[:100])
    items = [
        serialize_faculty_conversation(conv, viewer=viewer) for conv in conversations
    ]
    peer_ids_with_thread = {item["peer_id"] for item in items if item.get("peer_id")}
    peers = [
        serialize_faculty_peer(peer)
        for peer in faculty_peers_queryset(viewer)
        if peer.pk not in peer_ids_with_thread
    ]
    # Peers without threads appear after active threads.
    combined = items + peers

    active_id = active_conversation_id
    if active_id is not None and not any(
        i.get("conversation_id") == active_id for i in items
    ):
        active_id = None
    if active_id is None and items:
        active_id = items[0]["conversation_id"]

    return {
        "items": combined,
        "active_conversation_id": active_id,
    }


def post_faculty_message(
    conversation: FacultyConversation,
    author: User,
    *,
    body: str = "",
    image=None,
) -> FacultyMessage:
    """Append a message to a faculty DM thread and notify the peer."""
    if not professor_can_access_faculty_conversation(author, conversation):
        raise PermissionError("Not allowed.")
    body = (body or "").strip()
    if not body and not image:
        raise ValueError("Message must include text or an image.")

    message = FacultyMessage.objects.create(
        conversation=conversation,
        author=author,
        body=body,
        image=image,
    )
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["last_message_at"])

    peer = conversation.other_participant(author)
    author_name = author.get_full_name() or author.email
    create_notification(
        peer,
        f"{author_name} sent you a message",
        link=(
            reverse("analytics_professor:overview")
            + f"?open_chat=1&chat_tab=faculty&conversation_id={conversation.pk}"
        ),
    )
    return message

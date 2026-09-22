"""In-app notification helpers."""

from django.utils import timezone

from apps.users.models import Notification, User


def create_notification(user: User, message: str, link: str = "") -> Notification:
    return Notification.objects.create(user=user, message=message, link=link)


def unread_notification_count(user: User) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def recent_notifications(user: User, *, limit: int = 8) -> list[Notification]:
    """Recent notifications for the navbar dropdown (unread first)."""
    unread = list(
        Notification.objects.filter(user=user, read_at__isnull=True).order_by(
            "-created_at"
        )[:limit]
    )
    if len(unread) >= limit:
        return unread
    remaining = limit - len(unread)
    unread_ids = [n.pk for n in unread]
    read = list(
        Notification.objects.filter(user=user)
        .exclude(pk__in=unread_ids)
        .order_by("-created_at")[:remaining]
    )
    return unread + read


def mark_notifications_read(user: User, notification_ids: list[int] | None = None) -> int:
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    if notification_ids:
        qs = qs.filter(pk__in=notification_ids)
    return qs.update(read_at=timezone.now())


def notification_cta_label(notification: Notification) -> str:
    """Primary action label based on the notification link target."""
    link = (notification.link or "").lower()
    if "question" in link and "edit" in link:
        return "Edit question"
    if link:
        return "Open"
    return ""

"""In-app notification helpers."""

from django.utils import timezone

from apps.users.models import Notification, User


def create_notification(user: User, message: str, link: str = "") -> Notification:
    return Notification.objects.create(user=user, message=message, link=link)


def unread_notification_count(user: User) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_notifications_read(user: User, notification_ids: list[int] | None = None) -> int:
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    if notification_ids:
        qs = qs.filter(pk__in=notification_ids)
    return qs.update(read_at=timezone.now())

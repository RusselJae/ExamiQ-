"""User-related signals."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models import User


@receiver(post_save, sender=User)
def notify_on_pending_staff_registration(sender, instance: User, created: bool, **kwargs):
    """No-op: faculty are auto-approved; Campus Admin approval flow removed."""
    return

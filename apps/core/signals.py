"""Core signal handlers."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.core.audit import log_audit_event
from apps.core.models import AuditLog


@receiver(user_logged_in)
def audit_user_login(sender, request, user, **kwargs):
    log_audit_event(
        user,
        AuditLog.Action.LOGIN,
        target_user=user,
        message=f"{user.email} signed in",
    )

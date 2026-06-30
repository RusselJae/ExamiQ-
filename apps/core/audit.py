"""Audit logging helpers."""

from __future__ import annotations

from typing import Any

from apps.core.models import AuditLog


def log_audit_event(
    actor,
    action: str,
    *,
    target_user=None,
    message: str = "",
    target_type: str = "",
    target_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an auditable action."""
    actor_role = ""
    if actor is not None and hasattr(actor, "role"):
        actor_role = actor.role or ""
    return AuditLog.objects.create(
        actor=actor,
        actor_role=actor_role,
        action=action,
        target_user=target_user,
        target_type=target_type,
        target_id=target_id,
        message=message,
        metadata=metadata or {},
    )

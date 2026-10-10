"""Password reset throttling: cooldown and daily request limits."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.users.models import PasswordResetRequestLog, User


class PasswordResetThrottleError(Exception):
    """Raised when a reset request is blocked by cooldown or daily limit."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _cooldown_seconds() -> int:
    return int(getattr(settings, "PASSWORD_RESET_COOLDOWN_SECONDS", 30) or 30)


def _daily_limit() -> int:
    return int(getattr(settings, "PASSWORD_RESET_DAILY_LIMIT", 3) or 3)


def normalize_reset_email(email: str) -> str:
    return (email or "").strip().lower()


def email_has_account(email: str) -> bool:
    """True when an active (or pending) user exists for this email."""
    normalized = normalize_reset_email(email)
    if not normalized:
        return False
    return User.objects.filter(email__iexact=normalized).exists()


def check_password_reset_allowed(email: str) -> None:
    """Raise PasswordResetThrottleError when cooldown or daily limit blocks the request."""
    normalized = normalize_reset_email(email)
    now = timezone.now()
    cooldown = timedelta(seconds=_cooldown_seconds())
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    day_count = PasswordResetRequestLog.objects.filter(
        email=normalized,
        requested_at__gte=day_start,
    ).count()
    if day_count >= _daily_limit():
        raise PasswordResetThrottleError(
            "You have reached the maximum of three password reset requests for today. "
            "Please try again tomorrow.",
            status_code=429,
        )

    latest = (
        PasswordResetRequestLog.objects.filter(email=normalized)
        .order_by("-requested_at")
        .first()
    )
    if latest and now - latest.requested_at < cooldown:
        wait = int((cooldown - (now - latest.requested_at)).total_seconds())
        raise PasswordResetThrottleError(
            f"Please wait {max(wait, 1)} seconds before requesting another reset.",
            status_code=400,
        )


def record_password_reset_request(email: str, *, ip_address: str | None = None) -> None:
    """Persist a successful reset request for throttling accounting."""
    PasswordResetRequestLog.objects.create(
        email=normalize_reset_email(email),
        ip_address=ip_address or None,
    )

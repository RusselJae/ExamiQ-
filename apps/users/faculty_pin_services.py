"""Faculty signup PIN storage, verification, and change notifications."""

import hmac

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from apps.users.models import FacultySignupPinSettings, User


def _faculty_pin_matches(provided: str, expected: str) -> bool:
    """Constant-time PIN compare; unequal lengths never match."""
    if not expected or not provided:
        return False
    provided_b = provided.encode("utf-8")
    expected_b = expected.encode("utf-8")
    if len(provided_b) != len(expected_b):
        return False
    return hmac.compare_digest(provided_b, expected_b)


def _env_faculty_signup_pin() -> str:
    return (getattr(settings, "FACULTY_SIGNUP_PIN", "") or "").strip()


def faculty_signup_pin_is_configured() -> bool:
    """True when a PIN exists in the database or environment."""
    pin_settings = FacultySignupPinSettings.load()
    if pin_settings.pin_hash:
        return True
    return bool(_env_faculty_signup_pin())


def verify_faculty_signup_pin(provided: str) -> bool:
    """Validate a faculty signup PIN against the stored hash or env fallback."""
    provided_pin = (provided or "").strip()
    if not provided_pin:
        return False

    pin_settings = FacultySignupPinSettings.load()
    if pin_settings.pin_hash:
        return check_password(provided_pin, pin_settings.pin_hash)
    return _faculty_pin_matches(provided_pin, _env_faculty_signup_pin())


def get_faculty_signup_pin_status() -> dict:
    """Profile display metadata for the shared faculty signup PIN."""
    pin_settings = FacultySignupPinSettings.load()
    return {
        "is_configured": faculty_signup_pin_is_configured(),
        "updated_at": pin_settings.updated_at if pin_settings.pin_hash else None,
        "updated_by": pin_settings.updated_by if pin_settings.pin_hash else None,
    }


def get_faculty_notification_emails(*, exclude_user: User | None = None) -> list[str]:
    """Active faculty and chairperson emails for PIN change alerts."""
    qs = User.objects.filter(
        is_active=True,
        role__in=(User.Role.PROFESSOR, User.Role.CHAIRPERSON),
    ).exclude(email="")
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    return list(qs.values_list("email", flat=True).distinct())


def update_faculty_signup_pin(*, changed_by: User, new_pin: str) -> None:
    """Persist a new faculty signup PIN and notify other faculty accounts."""
    from apps.users.email_services import send_faculty_signup_pin_changed_email

    normalized_pin = (new_pin or "").strip()
    pin_settings = FacultySignupPinSettings.load()
    pin_settings.pin_hash = make_password(normalized_pin)
    pin_settings.updated_by = changed_by
    pin_settings.updated_at = timezone.now()
    pin_settings.save(
        update_fields=["pin_hash", "updated_by", "updated_at"],
    )

    recipients = get_faculty_notification_emails(exclude_user=changed_by)
    if recipients:
        send_faculty_signup_pin_changed_email(
            changed_by=changed_by,
            new_pin=normalized_pin,
            recipients=recipients,
        )

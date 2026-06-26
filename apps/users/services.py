"""User profile services."""

from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils import timezone

from allauth.account.adapter import get_adapter
from allauth.account.internal.flows.manage_email import email_already_exists
from allauth.account.models import EmailAddress

from apps.users.models import User


def count_active_sessions(user: User) -> int:
    """Return the number of non-expired sessions for this user."""
    user_id = str(user.pk)
    count = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get("_auth_user_id") == user_id:
            count += 1
    return count


def get_account_activity(user: User) -> dict:
    """Return display values for the profile account activity card."""
    password_changed_at = user.password_changed_at or user.date_joined
    session_count = count_active_sessions(user)
    device_label = "device" if session_count == 1 else "devices"
    return {
        "last_login": user.last_login,
        "password_changed_at": password_changed_at,
        "active_session_count": session_count,
        "active_session_label": f"{session_count} {device_label}",
    }


def request_email_change(request: HttpRequest, user: User, new_email: str) -> str:
    """Request an email change via allauth verification; does not update user.email yet."""
    adapter = get_adapter()
    email, _already_exists = email_already_exists(new_email, user=user)

    if email == user.email.lower():
        raise ValidationError("This is already your login email.")

    EmailAddress.objects.add_new_email(request, user, email)
    return "Check your inbox to confirm the new email."

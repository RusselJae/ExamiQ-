"""Account workflow email notifications."""

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string

from apps.users.models import User


def get_campus_admin_emails() -> list[str]:
    return list(
        User.objects.filter(is_active=True)
        .filter(Q(role=User.Role.CAMPUS_ADMIN) | Q(is_superuser=True))
        .values_list("email", flat=True)
        .distinct()
    )


def send_account_approved_email(user: User) -> None:
    site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")
    subject = "Your EXAMIQ+ account has been approved"
    body = render_to_string(
        "emails/account_approved.txt",
        {"user": user, "login_url": f"{site_url}/accounts/login/"},
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


def send_account_rejected_email(user: User) -> None:
    subject = "Your EXAMIQ+ registration was not approved"
    body = render_to_string("emails/account_rejected.txt", {"user": user})
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


def send_pending_registration_alert(user: User) -> None:
    admins = get_campus_admin_emails()
    if not admins:
        return
    site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")
    subject = f"New pending registration: {user.get_role_display()}"
    body = render_to_string(
        "emails/pending_registration_alert.txt",
        {
            "user": user,
            "review_url": f"{site_url}/campus/users/?status=pending",
        },
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, admins, fail_silently=True)

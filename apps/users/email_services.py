"""Account workflow email notifications."""

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.users.models import User


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


"""Unrecognized login detection and user notifications."""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.models import User, UserLoginFingerprint
from apps.users.notification_services import create_notification


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:45]
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote[:45] if remote else None


def _ua_hash(user_agent: str) -> str:
    return hashlib.sha256(user_agent.encode("utf-8", errors="replace")).hexdigest()


def process_login_fingerprint(request: HttpRequest, user: User) -> bool:
    """
    Record the current login fingerprint.

    Returns True when this is a new (unrecognized) fingerprint that should alert.
    The very first fingerprint for an account is recorded silently (no alert).
    """
    ip = _client_ip(request)
    raw_ua = (request.META.get("HTTP_USER_AGENT") or "")[:512]
    ua_hash = _ua_hash(raw_ua)

    existing = UserLoginFingerprint.objects.filter(
        user=user,
        ip_address=ip,
        user_agent_hash=ua_hash,
    ).first()
    if existing:
        existing.last_seen_at = timezone.now()
        existing.user_agent = raw_ua
        existing.save(update_fields=["last_seen_at", "user_agent"])
        return False

    had_prior = UserLoginFingerprint.objects.filter(user=user).exists()
    UserLoginFingerprint.objects.create(
        user=user,
        ip_address=ip,
        user_agent_hash=ua_hash,
        user_agent=raw_ua,
    )
    # First-ever fingerprint: establish baseline without alarming the user.
    return had_prior


def notify_unrecognized_login(request: HttpRequest, user: User) -> None:
    """Send in-app + email alert for a new login fingerprint."""
    when = timezone.localtime()
    ip = _client_ip(request) or "unknown"
    ua = (request.META.get("HTTP_USER_AGENT") or "unknown browser")[:120]
    when_label = when.strftime("%b %d, %Y %I:%M %p")

    message = (
        f"New sign-in detected on {when_label} from {ip}. "
        "If this wasn't you, change your password."
    )
    create_notification(user, message, link="/profile/")

    site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")
    subject = "EXAMIQ+ security alert: new sign-in"
    body = render_to_string(
        "emails/unrecognized_login.txt",
        {
            "user": user,
            "when_label": when_label,
            "ip_address": ip,
            "user_agent": ua,
            "profile_url": f"{site_url}/profile/",
        },
    )
    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )

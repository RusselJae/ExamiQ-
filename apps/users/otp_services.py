"""Signup email OTP generation, delivery, and verification."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.models import EmailSignupOTP, User

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
SIGNUP_OTP_SESSION_KEY = "signup_otp_user_id"
RESEND_API_URL = "https://api.resend.com/emails"


class SignupOTPError(Exception):
    """Raised when OTP send/verify fails with a user-facing message."""


def _hash_code(code: str) -> str:
    material = f"{settings.SECRET_KEY}:signup-otp:{code}".encode()
    return hashlib.sha256(material).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


def _resend_api_key() -> str:
    """Return Resend API key from dedicated setting or SMTP password fallback."""
    key = (getattr(settings, "RESEND_API_KEY", None) or "").strip()
    if key:
        return key
    password = (getattr(settings, "EMAIL_HOST_PASSWORD", None) or "").strip()
    if password.startswith("re_"):
        return password
    return ""


def _should_use_resend_api() -> bool:
    """Prefer HTTPS Resend API when configured (avoids PaaS SMTP timeouts)."""
    if not _resend_api_key():
        return False
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    return not (
        "locmem" in backend or "console" in backend or "dummy" in backend
    )


def _send_via_resend_api(
    *,
    subject: str,
    text_body: str,
    html_body: str,
    to_email: str,
) -> None:
    """Send email through Resend's HTTPS API."""
    api_key = _resend_api_key()
    payload = {
        "from": settings.DEFAULT_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    timeout = int(getattr(settings, "EMAIL_TIMEOUT", 15) or 15)
    request = urllib.request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise SignupOTPError(
                    "We could not send the verification email. Please try again."
                )
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}
            detail = str(data.get("message") or data.get("error") or body)[:200]
        except (TypeError, ValueError, AttributeError, OSError, json.JSONDecodeError):
            detail = str(exc.reason or exc)
        logger.warning("Resend API HTTP %s: %s", exc.code, detail)
        raise SignupOTPError(
            "We could not send the verification email. Check Resend API settings."
        ) from exc
    except urllib.error.URLError as exc:
        logger.warning("Resend API network error: %s", exc.reason)
        raise SignupOTPError(
            "We could not reach the email service. Please try again shortly."
        ) from exc
    except TimeoutError as exc:
        logger.warning("Resend API timed out")
        raise SignupOTPError(
            "Sending the verification email timed out. Please try again."
        ) from exc


def _deliver_otp_email(
    *,
    subject: str,
    text_body: str,
    html_body: str,
    to_email: str,
) -> None:
    """Deliver OTP via Resend HTTPS API when configured, else Django email backend."""
    if _should_use_resend_api():
        _send_via_resend_api(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            to_email=to_email,
        )
        return
    send_mail(
        subject,
        text_body,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
        html_message=html_body,
    )


def send_signup_otp(user: User, *, force: bool = False) -> EmailSignupOTP:
    """Create (or replace) an OTP for ``user`` and email it."""
    now = timezone.now()
    active = (
        EmailSignupOTP.objects.filter(user=user, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if active and not force and now - active.last_sent_at < OTP_RESEND_COOLDOWN:
        wait = int(
            (OTP_RESEND_COOLDOWN - (now - active.last_sent_at)).total_seconds()
        )
        raise SignupOTPError(
            f"Please wait {max(wait, 1)} seconds before requesting a new code."
        )

    EmailSignupOTP.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=now
    )

    code = _generate_code()
    otp = EmailSignupOTP.objects.create(user=user, code_hash=_hash_code(code))

    subject = "Your ExamiQ verification code"
    context = {
        "user": user,
        "code": code,
        "minutes": int(OTP_TTL.total_seconds() // 60),
    }
    text_body = render_to_string("emails/signup_otp.txt", context)
    html_body = render_to_string("emails/signup_otp.html", context)
    _deliver_otp_email(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to_email=user.email,
    )
    return otp


def verify_signup_otp(user: User, code: str) -> User:
    """Validate ``code`` and activate ``user``. Raises SignupOTPError on failure."""
    cleaned = (code or "").strip()
    if not cleaned.isdigit() or len(cleaned) != OTP_LENGTH:
        raise SignupOTPError("Enter the 6-digit code from your email.")

    otp = (
        EmailSignupOTP.objects.filter(user=user, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not otp:
        raise SignupOTPError("No verification code found. Request a new one.")

    if timezone.now() - otp.created_at > OTP_TTL:
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["consumed_at"])
        raise SignupOTPError("That code has expired. Request a new one.")

    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise SignupOTPError("Too many attempts. Request a new code.")

    otp.attempts += 1
    otp.save(update_fields=["attempts"])

    if not secrets.compare_digest(otp.code_hash, _hash_code(cleaned)):
        remaining = OTP_MAX_ATTEMPTS - otp.attempts
        if remaining <= 0:
            raise SignupOTPError("Too many attempts. Request a new code.")
        raise SignupOTPError(
            f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} left."
        )

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at"])

    user.is_active = True
    user.save(update_fields=["is_active"])

    from allauth.account.models import EmailAddress

    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"verified": True, "primary": True},
    )

    return user


def pending_signup_user(request) -> User | None:
    """Return the signup user stuck in session OTP flow, if any."""
    user_id = request.session.get(SIGNUP_OTP_SESSION_KEY)
    if not user_id:
        return None
    return (
        User.objects.filter(pk=user_id, is_active=False)
        .exclude(approval_status=User.ApprovalStatus.REJECTED)
        .first()
    )

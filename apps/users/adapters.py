from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.core.views import get_role_dashboard_url
from apps.users.models import User
from apps.users.otp_services import (
    SIGNUP_OTP_SESSION_KEY,
    SignupOTPError,
    _send_via_resend_api,
    _should_use_resend_api,
    login_otp_exempt,
)

import logging

logger = logging.getLogger(__name__)

# Faculty roles that must complete email OTP after password login.
_LOGIN_OTP_ROLES = frozenset(
    {User.Role.PROFESSOR, User.Role.PROGRAM_COORDINATOR, User.Role.CHAIRPERSON}
)


class EmailDeliveryError(Exception):
    """A transactional email could not be delivered.

    Transport failures (SMTP refused, Resend unreachable, bad credentials)
    used to escape as raw ``smtplib``/``OSError`` exceptions and turn the
    sign-in POST into an Internal Server Error. The auth views catch this and
    show a friendly message instead.
    """


class ExamiQAccountAdapter(DefaultAccountAdapter):
    """Redirect users to role-specific dashboards after login."""

    def get_login_redirect_url(self, request):
        if request.user.is_authenticated:
            return get_role_dashboard_url(request.user)
        return reverse("core:home")

    def get_signup_redirect_url(self, request):
        if request.session.get(SIGNUP_OTP_SESSION_KEY):
            return reverse("users:signup_verify")
        return super().get_signup_redirect_url(request)

    def is_login_by_code_required(self, login) -> bool:
        """Require email OTP for faculty/chairperson password logins."""
        try:
            from allauth.account import authentication

            request = getattr(self, "request", None)
            if request is not None:
                records = authentication.get_authentication_records(request)
                if records and records[-1].get("method") == "code":
                    return False
        except Exception:  # noqa: BLE001 — fall through to role check
            pass
        user = getattr(login, "user", None)
        if user is None:
            return False
        if login_otp_exempt(user):
            return False
        return getattr(user, "role", None) in _LOGIN_OTP_ROLES

    def _deliver(self, msg) -> None:
        """Send a message, turning transport failures into EmailDeliveryError."""
        try:
            msg.send()
        except Exception as exc:  # noqa: BLE001 — never 500 the auth flow
            logger.warning("Email delivery failed: %s", exc)
            raise EmailDeliveryError(
                "We could not send the email right now. Please try again shortly."
            ) from exc

    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        """Send allauth mail via Resend HTTPS when configured (same path as OTP)."""
        request = allauth_context.request
        ctx: dict[str, Any] = {
            "request": request,
            "email": email,
            "current_site": get_current_site(request),
        }
        ctx.update(context)
        msg = self.render_mail(template_prefix, email, ctx)

        if not _should_use_resend_api():
            self._deliver(msg)
            return

        text_body = msg.body or ""
        html_body = text_body
        if isinstance(msg, EmailMultiAlternatives) and msg.alternatives:
            for content, mimetype in msg.alternatives:
                if mimetype == "text/html":
                    html_body = content
                    break
        to_email = email if isinstance(email, str) else email[0]
        try:
            _send_via_resend_api(
                subject=msg.subject or "",
                text_body=text_body,
                html_body=html_body,
                to_email=to_email,
            )
        except SignupOTPError:
            self._deliver(msg)

    def respond_user_inactive(
        self, request: HttpRequest, user: AbstractBaseUser
    ) -> HttpResponse:
        approval_status = getattr(user, "approval_status", None)
        if approval_status == User.ApprovalStatus.PENDING:
            return redirect(f"{reverse('account_login')}?registered=pending")
        if approval_status == User.ApprovalStatus.REJECTED:
            return redirect(f"{reverse('account_login')}?registered=rejected")
        if getattr(user, "is_archived", False):
            return redirect(f"{reverse('account_login')}?archived=1")
        if approval_status == User.ApprovalStatus.APPROVED and not getattr(
            user, "is_active", True
        ):
            request.session[SIGNUP_OTP_SESSION_KEY] = user.pk
            return redirect("users:signup_verify")
        return super().respond_user_inactive(request, user)

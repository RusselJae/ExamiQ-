"""Signup email OTP verification views."""

from django.contrib import messages
from django.core.mail import BadHeaderError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.users.otp_services import (
    SIGNUP_OTP_SESSION_KEY,
    SignupOTPError,
    pending_signup_user,
    send_signup_otp,
    verify_signup_otp,
)


class SignupOTPVerifyView(View):
    """Verify the email address for a new student or faculty request."""

    template_name = "account/signup_otp.html"

    def get(self, request):
        user = pending_signup_user(request)
        if not user:
            messages.info(request, "Create an account first, then verify your email.")
            return redirect("account_signup")
        return render(
            request,
            self.template_name,
            {
                "email": user.email,
                "error": "",
                "awaiting_approval": user.approval_status
                == user.ApprovalStatus.PENDING,
            },
        )

    def post(self, request):
        user = pending_signup_user(request)
        if not user:
            messages.info(request, "Create an account first, then verify your email.")
            return redirect("account_signup")

        action = request.POST.get("action") or "verify"
        if action == "resend":
            try:
                send_signup_otp(user, force=False)
                messages.success(request, "A new code was sent to your email.")
            except SignupOTPError as exc:
                messages.error(request, str(exc))
            except (OSError, BadHeaderError, ConnectionError, TimeoutError):
                messages.error(
                    request,
                    "We could not send email right now. Please try again shortly.",
                )
            except Exception:  # noqa: BLE001 — never 500 the OTP resend UX
                messages.error(
                    request,
                    "We could not send email right now. Please try again shortly.",
                )
            return redirect("users:signup_verify")

        if action == "cancel":
            request.session.pop(SIGNUP_OTP_SESSION_KEY, None)
            messages.info(request, "Verification cancelled. You can sign in instead.")
            return redirect(reverse("account_login"))

        code = "".join(ch for ch in (request.POST.get("code") or "") if ch.isdigit())[:6]
        try:
            verify_signup_otp(user, code)
        except SignupOTPError as exc:
            return render(
                request,
                self.template_name,
                {
                    "email": user.email,
                    "error": str(exc),
                    "code": code,
                    "awaiting_approval": user.approval_status
                    == user.ApprovalStatus.PENDING,
                },
                status=400,
            )

        request.session.pop(SIGNUP_OTP_SESSION_KEY, None)
        if user.approval_status == user.ApprovalStatus.PENDING:
            messages.success(
                request,
                "Email verified. Your faculty account request is awaiting program coordinator approval.",
            )
            return redirect(f"{reverse('account_login')}?registered=pending")

        messages.success(request, "Email verified. You can sign in now.")
        return redirect(f"{reverse('account_login')}?verified=1")

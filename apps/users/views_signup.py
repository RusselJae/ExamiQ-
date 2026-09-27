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
    """Enter the emailed 6-digit code to activate a new account."""

    template_name = "account/signup_otp.html"

    def get(self, request):
        user = pending_signup_user(request)
        if not user:
            messages.info(request, "Create an account first, then verify your email.")
            return redirect("account_signup")
        return render(
            request,
            self.template_name,
            {"email": user.email, "error": ""},
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
                    "We could not send email right now. Check SMTP settings and try again.",
                )
            return redirect("users:signup_verify")

        code = request.POST.get("code", "")
        try:
            verify_signup_otp(user, code)
        except SignupOTPError as exc:
            return render(
                request,
                self.template_name,
                {"email": user.email, "error": str(exc), "code": code},
                status=400,
            )

        request.session.pop(SIGNUP_OTP_SESSION_KEY, None)
        messages.success(request, "Email verified. You can sign in now.")
        return redirect(f"{reverse('account_login')}?verified=1")

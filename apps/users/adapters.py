from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.core.views import get_role_dashboard_url
from apps.users.models import User
from apps.users.otp_services import SIGNUP_OTP_SESSION_KEY


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
        if (
            approval_status == User.ApprovalStatus.APPROVED
            and not getattr(user, "is_active", True)
        ):
            request.session[SIGNUP_OTP_SESSION_KEY] = user.pk
            return redirect("users:signup_verify")
        return super().respond_user_inactive(request, user)

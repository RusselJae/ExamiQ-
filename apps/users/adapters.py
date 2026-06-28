from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from allauth.account.adapter import DefaultAccountAdapter

from apps.core.views import get_role_dashboard_url
from apps.users.models import User


class ExamiQAccountAdapter(DefaultAccountAdapter):
    """Redirect users to role-specific dashboards after login."""

    def get_login_redirect_url(self, request):
        if request.user.is_authenticated:
            return get_role_dashboard_url(request.user)
        return reverse("core:home")

    def respond_user_inactive(
        self, request: HttpRequest, user: AbstractBaseUser
    ) -> HttpResponse:
        approval_status = getattr(user, "approval_status", None)
        if approval_status == User.ApprovalStatus.PENDING:
            return redirect(f"{reverse('account_login')}?registered=pending")
        if approval_status == User.ApprovalStatus.REJECTED:
            return redirect(f"{reverse('account_login')}?registered=rejected")
        return super().respond_user_inactive(request, user)

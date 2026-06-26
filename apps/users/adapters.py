from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse

from apps.core.views import get_role_dashboard_url


class ExamiQAccountAdapter(DefaultAccountAdapter):
    """Redirect users to role-specific dashboards after login."""

    def get_login_redirect_url(self, request):
        if request.user.is_authenticated:
            return get_role_dashboard_url(request.user)
        return reverse("core:home")

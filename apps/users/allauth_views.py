"""allauth view overrides that keep the auth pages reachable.

``RedirectAuthenticatedUserMixin`` — inherited by both allauth's ``LoginView``
and ``SignupView`` — redirects *any* GET back to ``account_confirm_login_code``
while a login-by-code stage is pending (``allauth/account/mixins.py``). A
faculty member who never receives (or does not enter) the emailed sign-in code
is therefore trapped: the sign-in page cannot be reopened, so they are pushed
back to the code screen forever.

Clearing the stashed login before allauth inspects the pending stage removes
that trap while keeping every other allauth behaviour intact.
"""

from __future__ import annotations

from allauth.account import views as allauth_views
from allauth.account.internal.stagekit import clear_login, get_pending_stage
from django.http import HttpRequest, HttpResponse

from apps.users.forms import (
    CoordinatorSignupForm,
    ExamiQSignupForm,
    FacultySignupForm,
)

__all__ = [
    "CoordinatorSignupView",
    "ExamiQFacultySignupView",
    "ExamiQLoginView",
    "ExamiQSignupView",
]


class ClearPendingLoginCodeMixin:
    """Drop a pending sign-in-code stage instead of redirecting to it."""

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        unauthenticated = not request.user.is_authenticated
        if unauthenticated and get_pending_stage(request) is not None:
            clear_login(request)
        return super().dispatch(request, *args, **kwargs)


class ExamiQLoginView(ClearPendingLoginCodeMixin, allauth_views.LoginView):
    """Sign-in page that always renders, even mid sign-in-code stage."""


class ExamiQSignupView(ClearPendingLoginCodeMixin, allauth_views.SignupView):
    """Student sign-up page that always renders, even mid sign-in-code stage."""

    form_class = ExamiQSignupForm


def _portal_token_valid(token: str, expected: str) -> bool:
    """True when the URL token matches the configured portal token."""
    import hmac

    expected = (expected or "").strip()
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


class SecretPortalMixin:
    """Gate unlisted registration pages behind a secret URL token."""

    portal_token_setting = ""
    portal_token_context = "portal_token"

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        from django.conf import settings
        from django.http import Http404

        expected = getattr(settings, self.portal_token_setting, "") or ""
        if not _portal_token_valid(kwargs.get("token", ""), expected):
            raise Http404()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.portal_token_context] = self.kwargs.get("token", "")
        context["portal_token"] = self.kwargs.get("token", "")
        return context


class ExamiQFacultySignupView(
    SecretPortalMixin, ClearPendingLoginCodeMixin, allauth_views.SignupView
):
    """Unlisted faculty account-request page (secret link only, not linked)."""

    portal_token_setting = "FACULTY_PORTAL_TOKEN"
    portal_token_context = "faculty_token"

    form_class = FacultySignupForm
    template_name = "account/faculty_signup.html"

    def get_form_class(self):
        """Bypass the global student signup form configured for allauth."""
        return FacultySignupForm


class CoordinatorPortalMixin(SecretPortalMixin):
    """Gate unlisted coordinator pages behind the secret URL token."""

    portal_token_setting = "COORDINATOR_PORTAL_TOKEN"
    portal_token_context = "coordinator_token"


class CoordinatorSignupView(
    CoordinatorPortalMixin, ClearPendingLoginCodeMixin, allauth_views.SignupView
):
    """Unlisted program-coordinator registration (secret link only, not linked)."""

    form_class = CoordinatorSignupForm
    template_name = "account/coordinator_signup.html"

    def get_form_class(self):
        return CoordinatorSignupForm

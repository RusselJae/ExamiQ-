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

__all__ = ["ExamiQLoginView", "ExamiQSignupView"]


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
    """Sign-up page that always renders, even mid sign-in-code stage."""

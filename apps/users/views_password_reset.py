"""Custom password-reset view with existence check and throttling."""

from allauth.account.views import PasswordResetView
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.users.adapters import EmailDeliveryError
from apps.users.password_reset_services import PasswordResetThrottleError


class ExamiQPasswordResetView(PasswordResetView):
    """Render a dedicated 429 page when the daily reset limit is exceeded."""

    def form_invalid(self, form):
        throttle = getattr(form, "throttle_error", None)
        if isinstance(throttle, PasswordResetThrottleError) and throttle.status_code == 429:
            return render(
                self.request,
                "account/password_reset_too_many.html",
                {"message": str(throttle)},
                status=429,
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except EmailDeliveryError:
            # The reset email could not be sent: never 500 the request.
            messages.error(
                self.request,
                "We could not send the reset email right now. Please try again in a moment.",
            )
            return redirect(reverse("account_reset_password"))

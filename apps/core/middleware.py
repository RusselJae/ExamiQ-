"""HTTP middleware for ExamiQ security headers."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse


class NoStoreForAuthenticatedMiddleware:
    """Prevent browsers from caching private HTML after logout / session expiry."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            content_type = response.get("Content-Type", "")
            if "text/html" in content_type or not content_type:
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"
        return response

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

from apps.users.models import User


def get_role_dashboard_url(user: User) -> str:
    """Return the dashboard URL for the given user's role."""
    if user.role == User.Role.STUDENT:
        return reverse("analytics_student:dashboard")
    if user.role == User.Role.PROFESSOR:
        return reverse("analytics_professor:overview")
    # Legacy chairperson accounts land on faculty overview; campus ops use Django admin.
    if user.role == User.Role.CHAIRPERSON:
        return reverse("analytics_professor:overview")
    return reverse("admin:index")


class HomeView(View):
    """Landing page for guests; dashboard redirect for signed-in users."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(get_role_dashboard_url(request.user))
        return render(request, "landing/home.html")


@method_decorator(csrf_exempt, name="dispatch")
class HealthCheckView(View):
    """Lightweight health probe for load balancers and uptime monitors."""

    @method_decorator(require_GET)
    def get(self, request):
        db_status = "ok"
        status_code = 200
        try:
            connection.ensure_connection()
        except Exception:
            db_status = "error"
            status_code = 503
        return JsonResponse(
            {"status": "ok" if db_status == "ok" else "degraded", "database": db_status},
            status=status_code,
        )

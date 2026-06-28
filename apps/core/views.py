from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.users.models import User


def get_role_dashboard_url(user: User) -> str:
    """Return the dashboard URL for the given user's role."""
    if user.role == User.Role.STUDENT:
        return reverse("analytics_student:dashboard")
    if user.role == User.Role.PROFESSOR:
        return reverse("analytics_professor:course_list")
    if user.role == User.Role.CHAIRPERSON:
        return reverse("analytics_chairperson:dashboard")
    return reverse("admin:index")


class HomeView(View):
    """Landing page for guests; dashboard redirect for signed-in users."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(get_role_dashboard_url(request.user))
        return render(request, "landing/home.html")

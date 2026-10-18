"""URL configuration for EXAMIQ."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import HealthCheckView
from apps.users.allauth_views import (
    CoordinatorSignupView,
    ExamiQFacultySignupView,
    ExamiQLoginView,
    ExamiQSignupView,
)
from apps.users.views_password_reset import ExamiQPasswordResetView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("admin/", admin.site.urls),
    # Override allauth password reset so daily-limit hits return HTTP 429.
    path(
        "accounts/password/reset/",
        ExamiQPasswordResetView.as_view(),
        name="account_reset_password",
    ),
    # Override allauth sign-in/sign-up so a pending login-by-code stage does not
    # bounce every GET back to the verification-code screen.
    path("accounts/login/", ExamiQLoginView.as_view(), name="account_login"),
    path("accounts/signup/", ExamiQSignupView.as_view(), name="account_signup"),
    path(
        "accounts/faculty/<str:token>/signup/",
        ExamiQFacultySignupView.as_view(),
        name="account_faculty_signup",
    ),
    # Unlisted coordinator registration — not linked anywhere; share privately.
    path(
        "accounts/coordinator/<str:token>/signup/",
        CoordinatorSignupView.as_view(),
        name="account_coordinator_signup",
    ),
    path("accounts/", include("allauth.urls")),
    path("profile/", include("apps.users.urls")),
    path("coordinator/", include("apps.users.urls_campus", namespace="campus")),
    path(
        "coordinator/",
        include("apps.analytics.urls_chairperson", namespace="analytics_chairperson"),
    ),
    path("coordinator/", include("apps.users.urls_coordinator", namespace="coordinator")),
    path("", include("apps.core.urls")),
    path("student/", include("apps.reviews.urls", namespace="reviews")),
    path("student/", include("apps.analytics.urls_student", namespace="analytics_student")),
    path("professor/", include("apps.analytics.urls_professor", namespace="analytics_professor")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

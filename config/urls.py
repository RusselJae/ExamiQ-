"""URL configuration for EXAMIQ."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("profile/", include("apps.users.urls")),
    path("campus/", include("apps.users.urls_campus")),
    path("", include("apps.core.urls")),
    path("student/", include("apps.reviews.urls", namespace="reviews")),
    path("student/", include("apps.analytics.urls_student", namespace="analytics_student")),
    path("professor/", include("apps.analytics.urls_professor", namespace="analytics_professor")),
    path("chairperson/", include("apps.analytics.urls_chairperson", namespace="analytics_chairperson")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

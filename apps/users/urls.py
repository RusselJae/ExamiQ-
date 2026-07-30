from django.urls import path

from apps.users.views import ProfileView
from apps.users.views_notifications import (
    NotificationListView,
    NotificationMarkLinkView,
    NotificationMarkReadView,
    NotificationOpenView,
    NotificationUnreadCountAPIView,
)
from apps.users.views_sections import ProgramSectionsAPIView

app_name = "users"

urlpatterns = [
    path("", ProfileView.as_view(), name="profile"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/read/", NotificationMarkReadView.as_view(), name="notifications_read"),
    path(
        "notifications/<int:pk>/open/",
        NotificationOpenView.as_view(),
        name="notification_open",
    ),
    path(
        "notifications/mark-link/",
        NotificationMarkLinkView.as_view(),
        name="notifications_mark_link",
    ),
    path("api/sections/", ProgramSectionsAPIView.as_view(), name="api_sections"),
    path("api/notifications/unread/", NotificationUnreadCountAPIView.as_view(), name="api_notifications_unread"),
]

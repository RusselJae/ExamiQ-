from django.urls import path

from apps.users.views import ProfileView
from apps.users.views_notifications import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationUnreadCountAPIView,
)
from apps.users.views_sections import ProgramSectionsAPIView

app_name = "users"

urlpatterns = [
    path("", ProfileView.as_view(), name="profile"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/read/", NotificationMarkReadView.as_view(), name="notifications_read"),
    path("api/sections/", ProgramSectionsAPIView.as_view(), name="api_sections"),
    path("api/notifications/unread/", NotificationUnreadCountAPIView.as_view(), name="api_notifications_unread"),
]

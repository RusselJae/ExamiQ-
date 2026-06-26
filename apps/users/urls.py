from django.urls import path

from apps.users.views import ProfileView

app_name = "users"

urlpatterns = [
    path("", ProfileView.as_view(), name="profile"),
]

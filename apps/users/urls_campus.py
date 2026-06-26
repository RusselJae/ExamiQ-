from django.urls import path

from apps.users import views_campus

app_name = "campus"

urlpatterns = [
    path("", views_campus.CampusDashboardView.as_view(), name="dashboard"),
    path("users/", views_campus.CampusUserListView.as_view(), name="user_list"),
    path(
        "users/create/professor/",
        views_campus.CampusCreateProfessorView.as_view(),
        name="create_professor",
    ),
    path(
        "users/create/chairperson/",
        views_campus.CampusCreateChairpersonView.as_view(),
        name="create_chairperson",
    ),
    path(
        "users/<int:pk>/toggle-active/",
        views_campus.CampusToggleUserActiveView.as_view(),
        name="toggle_active",
    ),
]

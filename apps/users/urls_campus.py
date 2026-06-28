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
    path(
        "users/<int:pk>/approve/",
        views_campus.CampusApproveUserView.as_view(),
        name="approve_user",
    ),
    path(
        "users/<int:pk>/reject/",
        views_campus.CampusRejectUserView.as_view(),
        name="reject_user",
    ),
    path("sections/", views_campus.CampusSectionListView.as_view(), name="section_list"),
    path("sections/create/", views_campus.CampusSectionCreateView.as_view(), name="section_create"),
    path("sections/bulk/", views_campus.CampusSectionBulkCreateView.as_view(), name="section_bulk"),
    path("sections/<int:pk>/edit/", views_campus.CampusSectionUpdateView.as_view(), name="section_edit"),
    path("academic-calendar/", views_campus.CampusAcademicCalendarView.as_view(), name="academic_calendar"),
]

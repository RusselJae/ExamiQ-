from django.urls import path

from apps.analytics import views_assignments, views_chairperson
from apps.users import views_chairperson as chairperson_users

app_name = "analytics_chairperson"

urlpatterns = [
    path("dashboard/", views_chairperson.ChairpersonDashboardView.as_view(), name="dashboard"),
    path("accounts/", chairperson_users.ChairpersonAccountListView.as_view(), name="accounts"),
    path(
        "accounts/<int:pk>/approve/",
        chairperson_users.ChairpersonApproveUserView.as_view(),
        name="account_approve",
    ),
    path(
        "accounts/<int:pk>/reject/",
        chairperson_users.ChairpersonRejectUserView.as_view(),
        name="account_reject",
    ),
    path(
        "accounts/<int:pk>/toggle-active/",
        chairperson_users.ChairpersonToggleUserActiveView.as_view(),
        name="account_toggle_active",
    ),
    path(
        "accounts/<int:pk>/archive/",
        chairperson_users.ChairpersonArchiveUserView.as_view(),
        name="account_archive",
    ),
    path(
        "accounts/<int:pk>/restore/",
        chairperson_users.ChairpersonRestoreUserView.as_view(),
        name="account_restore",
    ),
    path(
        "courses/subjects/",
        chairperson_users.ChairpersonSubjectListView.as_view(),
        name="subjects",
    ),
    path(
        "courses/subjects/<int:pk>/edit/",
        chairperson_users.ChairpersonSubjectUpdateView.as_view(),
        name="subject_edit",
    ),
    path(
        "courses/subjects/<int:pk>/delete/",
        chairperson_users.ChairpersonSubjectDeleteView.as_view(),
        name="subject_delete",
    ),
    path("assignments/", views_assignments.ChairpersonAssignmentListView.as_view(), name="assignments"),
    path(
        "assignments/create/",
        views_assignments.ChairpersonAssignmentCreateView.as_view(),
        name="assignment_create",
    ),
    path(
        "assignments/<int:pk>/delete/",
        views_assignments.ChairpersonAssignmentDeleteView.as_view(),
        name="assignment_delete",
    ),
    path(
        "assignments/api/subjects/",
        views_assignments.ChairpersonAssignmentSubjectsAPIView.as_view(),
        name="assignment_subjects_api",
    ),
    path(
        "assignments/api/sections/",
        views_assignments.ChairpersonAssignmentSectionsAPIView.as_view(),
        name="assignment_sections_api",
    ),
    path(
        "analytics/by-program/",
        views_chairperson.CrossProgramAnalyticsView.as_view(),
        name="analytics_by_program",
    ),
    path("courses/", views_chairperson.CourseAuditView.as_view(), name="course_audit"),
]

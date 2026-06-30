from django.urls import path

from apps.analytics import views_assignments, views_chairperson, views_chairperson_logs

app_name = "analytics_chairperson"

urlpatterns = [
    path("dashboard/", views_chairperson.ChairpersonDashboardView.as_view(), name="dashboard"),
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
    path("logs/faculty/", views_chairperson_logs.FacultyAuditLogView.as_view(), name="logs_faculty"),
    path("logs/students/", views_chairperson_logs.StudentAuditLogView.as_view(), name="logs_students"),
    path(
        "analytics/by-program/",
        views_chairperson.CrossProgramAnalyticsView.as_view(),
        name="analytics_by_program",
    ),
    path("courses/", views_chairperson.CourseAuditView.as_view(), name="course_audit"),
]

from django.urls import path

from apps.analytics import views_assignments, views_chairperson

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
    path("questions/review/", views_chairperson.QuestionReviewListView.as_view(), name="question_review"),
    path(
        "questions/review/<int:question_pk>/approve/",
        views_chairperson.QuestionReviewApproveView.as_view(),
        name="question_approve",
    ),
    path(
        "questions/review/<int:question_pk>/reject/",
        views_chairperson.QuestionReviewRejectView.as_view(),
        name="question_reject",
    ),
    path(
        "questions/review/<int:question_pk>/edit/",
        views_chairperson.QuestionReviewEditView.as_view(),
        name="question_review_edit",
    ),
    path(
        "analytics/by-program/",
        views_chairperson.CrossProgramAnalyticsView.as_view(),
        name="analytics_by_program",
    ),
    path("courses/", views_chairperson.CourseAuditView.as_view(), name="course_audit"),
]

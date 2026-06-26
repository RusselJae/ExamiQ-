from django.urls import path

from apps.analytics import views_student

app_name = "analytics_student"

urlpatterns = [
    path("dashboard/", views_student.StudentDashboardView.as_view(), name="dashboard"),
    path("sessions/", views_student.SessionHistoryView.as_view(), name="session_history"),
    path("topics/", views_student.TopicProgressView.as_view(), name="topic_progress"),
    path("mistakes/", views_student.MistakeListView.as_view(), name="mistakes"),
    path("mistakes/patterns/", views_student.MistakePatternView.as_view(), name="mistake_patterns"),
]

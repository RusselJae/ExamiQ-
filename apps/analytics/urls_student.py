from django.urls import path

from apps.analytics import views_student

app_name = "analytics_student"

urlpatterns = [
    path("dashboard/", views_student.StudentDashboardView.as_view(), name="dashboard"),
    path("sessions/", views_student.SessionHistoryView.as_view(), name="session_history"),
    path("chat/", views_student.StudentChatInboxView.as_view(), name="chat_inbox"),
    path(
        "chat/concerns/",
        views_student.StudentChatConcernsApiView.as_view(),
        name="chat_concerns_api",
    ),
    path("topics/", views_student.TopicProgressView.as_view(), name="topic_progress"),
    path("mistakes/", views_student.MistakeListView.as_view(), name="mistakes"),
    path(
        "mistakes/answers/<int:answer_pk>/",
        views_student.AnswerDetailView.as_view(),
        name="answer_detail",
    ),
    path(
        "mistakes/answers/<int:answer_pk>/concern/",
        views_student.UploadMistakeConcernView.as_view(),
        name="upload_mistake_concern",
    ),
    path(
        "mistakes/answers/<int:answer_pk>/generate-feedback/",
        views_student.GenerateAnswerFeedbackView.as_view(),
        name="generate_answer_feedback",
    ),
    path("mistakes/patterns/", views_student.MistakePatternView.as_view(), name="mistake_patterns"),
    path(
        "mistakes/patterns/<int:topic_id>/",
        views_student.TopicAnswerReviewView.as_view(),
        name="topic_answer_review",
    ),
]

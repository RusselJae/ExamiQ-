from django.urls import path

from apps.analytics import views_student

app_name = "analytics_student"

urlpatterns = [
    path("dashboard/", views_student.StudentDashboardView.as_view(), name="dashboard"),
    path("sessions/", views_student.SessionHistoryView.as_view(), name="session_history"),
    path("chat/", views_student.StudentChatInboxView.as_view(), name="chat_inbox"),
    path(
        "chat/conversations/",
        views_student.StudentChatConversationsApiView.as_view(),
        name="chat_conversations_api",
    ),
    path(
        "chat/concerns/",
        views_student.StudentChatConversationsApiView.as_view(),
        name="chat_concerns_api",
    ),
    path(
        "chat/message/",
        views_student.StudentChatMessageView.as_view(),
        name="chat_message",
    ),
    path("topics/", views_student.TopicProgressView.as_view(), name="topic_progress"),
    path("mistakes/", views_student.MistakeListView.as_view(), name="mistakes"),
    path(
        "mistakes/concepts/<int:pk>/",
        views_student.ConceptReviewDetailView.as_view(),
        name="concept_review",
    ),
    path(
        "mistakes/concepts/<int:pk>/continue/",
        views_student.ConceptReviewContinueView.as_view(),
        name="concept_review_continue",
    ),
    path(
        "mistakes/concepts/<int:pk>/try-it/",
        views_student.ConceptReviewTryItView.as_view(),
        name="concept_review_try_it",
    ),
    path(
        "mistakes/concepts/<int:pk>/practice/",
        views_student.ConceptReviewPracticeView.as_view(),
        name="concept_review_practice",
    ),
    path(
        "mistakes/concepts/<int:pk>/review-again/",
        views_student.ConceptReviewAgainView.as_view(),
        name="concept_review_again",
    ),
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
    path(
        "materials/",
        views_student.StudentMaterialHubView.as_view(),
        name="materials_hub",
    ),
    path(
        "materials/<int:subject_pk>/",
        views_student.StudentMaterialListView.as_view(),
        name="materials_list",
    ),
    path(
        "materials/<int:subject_pk>/download/<int:pk>/",
        views_student.StudentMaterialDownloadView.as_view(),
        name="materials_download",
    ),
]

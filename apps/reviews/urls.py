from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    path("review/setup/", views.ReviewSetupView.as_view(), name="setup"),
    path("review/setup/subjects/", views.ReviewSetupSubjectsView.as_view(), name="setup_subjects"),
    path("review/setup/topics/", views.ReviewSetupTopicsView.as_view(), name="setup_topics"),
    path("review/setup/timing/", views.ReviewSetupTimingView.as_view(), name="setup_timing"),
    path("review/setup/preview/", views.ReviewSetupPreviewAPIView.as_view(), name="setup_preview"),
    path("review/<int:pk>/", views.ReviewSessionView.as_view(), name="session"),
    path("review/<int:pk>/question/", views.QuestionPartialView.as_view(), name="question_partial"),
    path(
        "review/<int:pk>/answer/<int:question_id>/",
        views.SubmitAnswerView.as_view(),
        name="submit_answer",
    ),
    path(
        "review/<int:pk>/feedback/<int:answer_id>/",
        views.FeedbackViewView.as_view(),
        name="feedback_view",
    ),
    path(
        "review/<int:pk>/feedback/<int:answer_id>/step/<int:step_id>/",
        views.StepFeedbackViewView.as_view(),
        name="step_feedback_view",
    ),
    path("review/<int:pk>/summary/", views.SessionSummaryView.as_view(), name="summary"),
    path("review/<int:pk>/results/", views.ExamResultsPartialView.as_view(), name="exam_results"),
    path(
        "review/<int:pk>/generate-feedback/",
        views.SessionGenerateFeedbackView.as_view(),
        name="session_generate_feedback",
    ),
    path("review/<int:pk>/tutor/history/", views.SessionTutorHistoryView.as_view(), name="tutor_history"),
    path("review/<int:pk>/tutor/chat/", views.SessionTutorChatView.as_view(), name="tutor_chat"),
    path("review/<int:pk>/expire/", views.SessionExpireView.as_view(), name="expire"),
]

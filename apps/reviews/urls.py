from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    path("review/setup/", views.ReviewSetupView.as_view(), name="setup"),
    path("review/setup/subjects/", views.ReviewSetupSubjectsView.as_view(), name="setup_subjects"),
    path("review/setup/topics/", views.ReviewSetupTopicsView.as_view(), name="setup_topics"),
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
    path("review/<int:pk>/expire/", views.SessionExpireView.as_view(), name="expire"),
]

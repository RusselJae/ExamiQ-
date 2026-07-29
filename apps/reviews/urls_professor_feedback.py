from django.urls import path

from apps.reviews import views_professor_feedback

app_name = "reviews_professor_feedback"

urlpatterns = [
    path("", views_professor_feedback.FeedbackListView.as_view(), name="feedback_list"),
]

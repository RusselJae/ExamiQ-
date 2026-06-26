from django.urls import path

from apps.questions import views_professor

app_name = "questions_professor"

urlpatterns = [
    path("", views_professor.QuestionListView.as_view(), name="question_list"),
    path("create/", views_professor.QuestionCreateView.as_view(), name="question_create"),
    path("<int:question_pk>/edit/", views_professor.QuestionUpdateView.as_view(), name="question_edit"),
    path("<int:question_pk>/delete/", views_professor.QuestionDeleteView.as_view(), name="question_delete"),
]

from django.urls import path

from apps.reviews import views_professor

app_name = "reviews_professor"

urlpatterns = [
    path("", views_professor.ReviewWindowListView.as_view(), name="window_list"),
    path("create/", views_professor.ReviewWindowCreateView.as_view(), name="window_create"),
    path("<int:window_pk>/edit/", views_professor.ReviewWindowUpdateView.as_view(), name="window_edit"),
    path("<int:window_pk>/delete/", views_professor.ReviewWindowDeleteView.as_view(), name="window_delete"),
]

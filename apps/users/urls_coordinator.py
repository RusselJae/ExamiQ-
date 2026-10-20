"""Program coordinator URLs."""

from django.urls import path

from apps.users.views_coordinator import (
    ProgramCoordinatorSubjectDeleteView,
    ProgramCoordinatorSubjectListView,
    ProgramCoordinatorSubjectUpdateView,
)

app_name = "coordinator"

urlpatterns = [
    path("subjects/", ProgramCoordinatorSubjectListView.as_view(), name="subject_list"),
    path(
        "subjects/<int:pk>/edit/",
        ProgramCoordinatorSubjectUpdateView.as_view(),
        name="subject_edit",
    ),
    path(
        "subjects/<int:pk>/delete/",
        ProgramCoordinatorSubjectDeleteView.as_view(),
        name="subject_delete",
    ),
]

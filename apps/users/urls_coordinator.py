"""Program coordinator URLs."""

from django.urls import path

from apps.users.views_coordinator import ProgramCoordinatorSubjectListView

app_name = "coordinator"

urlpatterns = [
    path("subjects/", ProgramCoordinatorSubjectListView.as_view(), name="subject_list"),
]

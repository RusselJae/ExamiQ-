"""Program coordinator curriculum-management views."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, UpdateView

from apps.core.mixins import ProgramCoordinatorRequiredMixin
from apps.questions.models import Subject
from apps.users.assignment_services import (
    create_curriculum_subject,
    delete_curriculum_subject,
)
from apps.users.forms import ChairpersonSubjectForm, ProgramCoordinatorSubjectForm
from apps.users.models import User


def _managed_subjects(user: User):
    """Return subjects belonging to programs managed by the coordinator."""
    subjects = Subject.objects.all()
    if user.department_id:
        return subjects.filter(program__managing_department=user.department)
    return subjects.none()


class ProgramCoordinatorSubjectListView(ProgramCoordinatorRequiredMixin, ListView):
    """List and create subjects for programs managed by the coordinator."""

    template_name = "coordinator/subjects/list.html"
    context_object_name = "subjects"
    paginate_by = 25

    def get_queryset(self):
        return (
            _managed_subjects(self.request.user)
            .select_related("program", "year_level")
            .order_by("program__name", "year_level__order", "semester", "code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get(
            "form", ProgramCoordinatorSubjectForm(coordinator=self.request.user)
        )
        return context

    def post(self, request, *args, **kwargs):
        form = ProgramCoordinatorSubjectForm(request.POST, coordinator=request.user)
        if not form.is_valid():
            return render(request, self.template_name, self.get_context_data(form=form))

        subject = create_curriculum_subject(
            program=form.cleaned_data["program"],
            code=form.cleaned_data["code"],
            name=form.cleaned_data["name"],
            year_level=form.cleaned_data["year_level"],
            semester=form.cleaned_data["semester"],
        )
        messages.success(
            request,
            f"{subject.code} — {subject.name} was added to the subject catalog.",
        )
        return redirect("coordinator:subject_list")


class ProgramCoordinatorSubjectUpdateView(ProgramCoordinatorRequiredMixin, UpdateView):
    """Edit a subject within the coordinator's managed programs."""

    model = Subject
    form_class = ChairpersonSubjectForm
    template_name = "coordinator/subjects/form.html"
    success_url = reverse_lazy("coordinator:subject_list")

    def get_queryset(self):
        return _managed_subjects(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["manager"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"{form.instance.code} updated.")
        return super().form_valid(form)


class ProgramCoordinatorSubjectDeleteView(ProgramCoordinatorRequiredMixin, View):
    """Remove a subject from the coordinator's managed programs."""

    def post(self, request, pk):
        subject = get_object_or_404(_managed_subjects(request.user), pk=pk)
        code = delete_curriculum_subject(subject)
        messages.success(request, f"{code} removed from the subject catalog.")
        return redirect("coordinator:subject_list")

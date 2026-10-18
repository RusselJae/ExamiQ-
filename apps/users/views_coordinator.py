"""Program coordinator curriculum-management views."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.generic import ListView

from apps.core.mixins import ProgramCoordinatorRequiredMixin
from apps.questions.models import Subject
from apps.users.assignment_services import create_curriculum_subject
from apps.users.forms import ProgramCoordinatorSubjectForm


class ProgramCoordinatorSubjectListView(ProgramCoordinatorRequiredMixin, ListView):
    """List and create subjects for programs managed by the coordinator."""

    template_name = "coordinator/subjects/list.html"
    context_object_name = "subjects"
    paginate_by = 25

    def get_queryset(self):
        return (
            Subject.objects.filter(
                program__managing_department=self.request.user.department
            )
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

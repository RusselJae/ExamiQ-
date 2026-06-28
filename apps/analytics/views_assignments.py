"""Chairperson teaching assignment views."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView

from apps.core.filtering import get_filter_param
from apps.core.mixins import ChairpersonRequiredMixin
from apps.questions.curriculum import subjects_for_teaching_assignment
from apps.users.assignment_services import create_teaching_assignment
from apps.users.forms import TeachingAssignmentForm
from apps.users.models import AcademicTerm, ProgramSection, TeachingAssignment


class ChairpersonAssignmentListView(ChairpersonRequiredMixin, ListView):
    template_name = "chairperson/assignments/list.html"
    context_object_name = "assignments"
    paginate_by = 25

    def _base_queryset(self):
        qs = (
            TeachingAssignment.objects.select_related(
                "professor",
                "program_section__program",
                "program_section__year_level",
                "program_section__academic_year",
                "subject",
                "term__academic_year",
            )
            .order_by("-term__academic_year__label", "term__name", "program_section__label")
        )
        dept_id = self.request.user.department_id
        if dept_id:
            qs = qs.filter(program_section__program__managing_department_id=dept_id)
        return qs

    def get_queryset(self):
        qs = self._base_queryset()
        term_filter = get_filter_param(self.request, "term")
        if term_filter == "1st":
            qs = qs.filter(term__name__icontains="1st")
        elif term_filter == "2nd":
            qs = qs.filter(term__name__icontains="2nd")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_qs = self._base_queryset()
        context["assignment_form"] = TeachingAssignmentForm(chairperson=self.request.user)
        context["term_filter"] = get_filter_param(self.request, "term")
        context["assignment_stats"] = {
            "total": base_qs.count(),
            "faculty": base_qs.values("professor_id").distinct().count(),
            "sections": base_qs.values("program_section_id").distinct().count(),
        }
        context["term_tabs"] = [
            {"key": "", "label": "All"},
            {"key": "1st", "label": "1st Sem"},
            {"key": "2nd", "label": "2nd Sem"},
        ]
        return context


class ChairpersonAssignmentCreateView(ChairpersonRequiredMixin, FormView):
    form_class = TeachingAssignmentForm
    template_name = "chairperson/assignments/list.html"
    success_url = reverse_lazy("analytics_chairperson:assignments")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["chairperson"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            create_teaching_assignment(
                professor=form.cleaned_data["professor"],
                program_section=form.cleaned_data["program_section"],
                subject=form.cleaned_data["subject"],
                term=form.cleaned_data["term"],
                assigned_by=self.request.user,
            )
        except ValueError as exc:
            messages.error(self.request, str(exc))
            return redirect("analytics_chairperson:assignments")
        messages.success(self.request, "Teaching assignment created.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Could not create assignment. Check the form.")
        return redirect("analytics_chairperson:assignments")


class ChairpersonAssignmentDeleteView(ChairpersonRequiredMixin, View):
    def post(self, request, pk):
        assignment = TeachingAssignment.objects.select_related(
            "program_section__program"
        ).filter(pk=pk).first()
        if not assignment:
            messages.error(request, "Assignment not found.")
            return redirect("analytics_chairperson:assignments")

        dept_id = request.user.department_id
        if dept_id and assignment.program_section.program.managing_department_id != dept_id:
            messages.error(request, "You cannot remove assignments outside your department.")
            return redirect("analytics_chairperson:assignments")

        assignment.delete()
        messages.success(request, "Teaching assignment removed.")
        return redirect("analytics_chairperson:assignments")


class ChairpersonAssignmentSubjectsAPIView(ChairpersonRequiredMixin, View):
    """GET ?section=<pk>&term=<pk> — subjects for a program section and term."""

    def get(self, request):
        from django.http import JsonResponse

        section_id = request.GET.get("section", "")
        term_id = request.GET.get("term", "")
        if not section_id.isdigit():
            return JsonResponse({"subjects": []})

        section = ProgramSection.objects.filter(pk=int(section_id)).select_related("program").first()
        if not section:
            return JsonResponse({"subjects": []})

        dept_id = request.user.department_id
        if dept_id and section.program.managing_department_id != dept_id:
            return JsonResponse({"subjects": []})

        term = None
        if term_id.isdigit():
            term = AcademicTerm.objects.filter(pk=int(term_id)).first()
        if not term:
            term = AcademicTerm.get_current()
        if not term:
            return JsonResponse({"subjects": []})

        subjects = subjects_for_teaching_assignment(section, term)
        return JsonResponse({
            "subjects": [
                {"id": s.pk, "code": s.code, "name": s.name, "label": str(s)}
                for s in subjects
            ]
        })

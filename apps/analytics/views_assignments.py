"""Chairperson teaching assignment views."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView

from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
)
from apps.core.audit import log_audit_event
from apps.core.models import AuditLog
from apps.core.mixins import ChairpersonRequiredMixin
from apps.questions.curriculum import subjects_for_teaching_assignment
from apps.questions.models import Subject
from apps.users.assignment_services import create_teaching_assignments
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
        qs = apply_date_range(qs, self.request, "created_at")
        qs = apply_sort(
            qs,
            self.request,
            newest_field="-created_at",
            oldest_field="created_at",
        )
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
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "sort",
                    "name": "sort",
                    "label": "Order",
                    "choices": [
                        ("newest", "Newest first"),
                        ("oldest", "Oldest first"),
                    ],
                },
                *STANDARD_DATE_SORT_FILTER_SPECS[0:2],
            ],
        )
        context["filter_has_active"] = has_active_filters(
            self.request, ["term", "date_from", "date_to", "sort"]
        )
        context["filter_bar_compact"] = True
        current_term = AcademicTerm.get_current()
        context["current_term_label"] = str(current_term) if current_term else "Current term"
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
            result = create_teaching_assignments(
                professor=form.cleaned_data["professor"],
                program_sections=form.cleaned_data["program_sections"],
                subject=form.cleaned_data["subject"],
                term=form.cleaned_data["term"],
                assigned_by=self.request.user,
            )
        except ValueError as exc:
            messages.error(self.request, str(exc))
            return redirect("analytics_chairperson:assignments")
        created = result["created"]
        skipped = result["skipped"]
        if created and skipped:
            messages.success(
                self.request,
                f"Created {created} assignment(s); {skipped} already existed.",
            )
        elif created:
            messages.success(
                self.request,
                f"Created {created} teaching assignment(s).",
            )
        else:
            messages.info(self.request, "All selected assignments already exist.")
        if created:
            log_audit_event(
                self.request.user,
                AuditLog.Action.ASSIGNMENT_CREATE,
                target_user=form.cleaned_data["professor"],
                message=(
                    f"Assigned {form.cleaned_data['professor'].email} to {created} section(s) "
                    f"for {form.cleaned_data['subject'].code}"
                ),
                metadata={"created": created, "skipped": skipped},
            )
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

        professor = assignment.professor
        section_label = assignment.program_section.display_label
        subject_code = assignment.subject.code
        assignment.delete()
        log_audit_event(
            request.user,
            AuditLog.Action.ASSIGNMENT_DELETE,
            target_user=professor,
            message=f"Removed assignment: {professor.email} — {section_label} — {subject_code}",
        )
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


class ChairpersonAssignmentSectionsAPIView(ChairpersonRequiredMixin, View):
    """GET ?subject=&term= — sections grouped by year with assignment state."""

    def get(self, request):
        subject_id = request.GET.get("subject", "")
        term_id = request.GET.get("term", "")
        if not subject_id.isdigit():
            return JsonResponse({"groups": []})

        subject = Subject.objects.filter(pk=int(subject_id)).select_related("program").first()
        if not subject:
            return JsonResponse({"groups": []})

        dept_id = request.user.department_id
        if dept_id and subject.program.managing_department_id != dept_id:
            return JsonResponse({"groups": []})

        term = AcademicTerm.objects.filter(pk=int(term_id)).first() if term_id.isdigit() else None
        if not term:
            term = AcademicTerm.get_current()
        if not term:
            return JsonResponse({"groups": []})

        sections = (
            ProgramSection.queryset_with_counts()
            .filter(program=subject.program, is_active=True)
            .select_related("year_level")
            .order_by("year_level__order", "label")
        )
        assigned_ids = set(
            TeachingAssignment.objects.filter(subject=subject, term=term).values_list(
                "program_section_id", flat=True
            )
        )

        groups: dict[str, dict] = {}
        for section in sections:
            year_name = section.year_level.name if section.year_level else "Other"
            if year_name not in groups:
                groups[year_name] = {"year": year_name, "sections": []}
            groups[year_name]["sections"].append(
                {
                    "id": section.pk,
                    "label": f"Section {section.label}",
                    "student_count": section.student_count,
                    "already_assigned": section.pk in assigned_ids,
                }
            )
        return JsonResponse({"groups": list(groups.values())})

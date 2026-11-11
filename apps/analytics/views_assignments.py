"""Chairperson teaching assignment views."""

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.core.audit import log_audit_event
from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
    redirect_preserving_filters,
)
from apps.core.mixins import AcademicManagerRequiredMixin
from apps.core.models import AuditLog
from apps.questions.curriculum import subjects_for_teaching_assignment
from apps.questions.models import Subject
from apps.users.assignment_services import (
    create_teaching_assignments,
    reassign_teaching_assignment,
)
from apps.users.forms import TeachingAssignmentForm
from apps.users.models import AcademicTerm, ProgramSection, TeachingAssignment, User


class ChairpersonAssignmentListView(AcademicManagerRequiredMixin, TemplateView):
    template_name = "chairperson/assignments/list.html"

    def _base_queryset(self):
        qs = TeachingAssignment.objects.select_related(
            "professor",
            "program_section__program",
            "program_section__year_level",
            "program_section__academic_year",
            "subject",
            "term__academic_year",
        ).order_by(
            "-term__academic_year__label",
            "term__name",
            "subject__code",
            "program_section__label",
        )
        dept_id = self.request.user.department_id
        if dept_id:
            qs = qs.filter(program_section__program__managing_department_id=dept_id)
        return qs

    def _term_filter(self) -> str:
        return get_filter_param(self.request, "term")

    def get_context_data(self, **kwargs):
        from collections import defaultdict

        from django.core.paginator import Paginator

        context = super().get_context_data(**kwargs)
        dept_id = self.request.user.department_id
        faculty_qs = User.objects.filter(
            role=User.Role.PROFESSOR, is_archived=False
        ).select_related("department")
        if dept_id:
            faculty_qs = faculty_qs.filter(department_id=dept_id)
        search = get_filter_param(self.request, "q").strip()
        if search:
            faculty_qs = faculty_qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(employee_id__icontains=search)
            )
        faculty_qs = faculty_qs.order_by("first_name", "last_name", "email")

        term_filter = self._term_filter()
        assignments_qs = self._base_queryset()
        if term_filter == "1st":
            assignments_qs = assignments_qs.filter(term__name__icontains="1st")
        elif term_filter == "2nd":
            assignments_qs = assignments_qs.filter(term__name__icontains="2nd")

        by_professor: dict[int, list] = defaultdict(list)
        for assignment in assignments_qs:
            by_professor[assignment.professor_id].append(assignment)

        rows = []
        for professor in faculty_qs:
            rows.append(
                {
                    "professor": professor,
                    "assignments": by_professor.get(professor.pk, []),
                    "course_count": len(
                        {a.subject_id for a in by_professor.get(professor.pk, [])}
                    ),
                    "section_count": len(
                        {
                            a.program_section_id
                            for a in by_professor.get(professor.pk, [])
                        }
                    ),
                }
            )

        paginator = Paginator(rows, 25)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context["faculty_rows"] = page_obj.object_list
        context["page_obj"] = page_obj
        context["assignment_form"] = TeachingAssignmentForm(
            chairperson=self.request.user
        )
        context["term_filter"] = term_filter
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search faculty",
                    "placeholder": "Search faculty…",
                },
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
        context["filter_preserve_params"] = (
            [("term", term_filter)] if term_filter else []
        )
        current_term = AcademicTerm.get_current()
        context["current_term_label"] = (
            str(current_term) if current_term else "Current term"
        )
        context["assignment_stats"] = {
            "total": assignments_qs.count(),
            "faculty": len({a.professor_id for a in assignments_qs}),
            "sections": len({a.program_section_id for a in assignments_qs}),
        }
        context["term_tabs"] = [
            {"key": "", "label": "All"},
            {"key": "1st", "label": "1st Sem"},
            {"key": "2nd", "label": "2nd Sem"},
        ]
        reassign_professors = User.objects.filter(
            role=User.Role.PROFESSOR, is_active=True
        ).order_by("email")
        if dept_id:
            reassign_professors = reassign_professors.filter(department_id=dept_id)
        context["reassign_professors"] = reassign_professors
        return context


class ChairpersonAssignmentCreateView(AcademicManagerRequiredMixin, FormView):
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
                    f"Assigned {form.cleaned_data['professor'].email} to "
                    f"{form.cleaned_data['subject'].code}"
                ),
                metadata={"created": created, "skipped": skipped},
            )
        return super().form_valid(form)

    def form_invalid(self, form):
        detail = ""
        for errors in form.errors.values():
            if errors:
                detail = str(errors[0])
                break
        if not detail and form.non_field_errors():
            detail = str(form.non_field_errors()[0])
        if detail:
            messages.error(self.request, detail)
        else:
            messages.error(self.request, "Could not create assignment. Check the form.")
        return redirect("analytics_chairperson:assignments")


class ChairpersonAssignmentDeleteView(AcademicManagerRequiredMixin, View):
    def post(self, request, pk):
        assignment = (
            TeachingAssignment.objects.select_related("program_section__program")
            .filter(pk=pk)
            .first()
        )
        if not assignment:
            messages.error(request, "Assignment not found.")
            return redirect_preserving_filters(
                request, "analytics_chairperson:assignments"
            )

        dept_id = request.user.department_id
        if (
            dept_id
            and assignment.program_section.program.managing_department_id != dept_id
        ):
            messages.error(
                request, "You cannot remove assignments outside your department."
            )
            return redirect_preserving_filters(
                request, "analytics_chairperson:assignments"
            )

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
        return redirect_preserving_filters(request, "analytics_chairperson:assignments")


class ChairpersonAssignmentReassignView(AcademicManagerRequiredMixin, View):
    """Move a teaching assignment to a different professor.

    Used when next year's (or this year's) teaching load changes hands.
    StudentFacultyAssignment rows are untouched — handled-student visibility
    follows the new professor from here on.
    """

    template_name = "chairperson/assignments/reassign.html"

    def _get_assignment(self, pk):
        return (
            TeachingAssignment.objects.select_related(
                "professor",
                "program_section__program",
                "program_section__year_level",
                "program_section__academic_year",
                "subject",
                "term__academic_year",
            )
            .filter(pk=pk)
            .first()
        )

    def _check_department(self, request, assignment):
        dept_id = request.user.department_id
        if dept_id and (
            assignment.program_section.program.managing_department_id != dept_id
        ):
            messages.error(
                request, "You cannot reassign teaching outside your department."
            )
            return False
        return True

    def _professor_choices(self, request):
        qs = User.objects.filter(role=User.Role.PROFESSOR, is_active=True)
        dept_id = request.user.department_id
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        return qs.order_by("email")

    def get(self, request, pk):
        from django.shortcuts import render

        assignment = self._get_assignment(pk)
        if not assignment:
            messages.error(request, "Assignment not found.")
            return redirect("analytics_chairperson:assignments")
        if not self._check_department(request, assignment):
            return redirect("analytics_chairperson:assignments")
        return render(
            request,
            self.template_name,
            {
                "assignment": assignment,
                "professors": self._professor_choices(request),
            },
        )

    def post(self, request, pk):
        assignment = self._get_assignment(pk)
        if not assignment:
            messages.error(request, "Assignment not found.")
            return redirect("analytics_chairperson:assignments")
        if not self._check_department(request, assignment):
            return redirect("analytics_chairperson:assignments")
        professor_pk = (request.POST.get("professor") or "").strip()
        if not professor_pk.isdigit():
            messages.error(request, "Choose the faculty member to reassign to.")
            return redirect("analytics_chairperson:assignment_reassign", pk=pk)
        choices = self._professor_choices(request)
        professor = choices.filter(pk=int(professor_pk)).first()
        if professor is None:
            messages.error(request, "Choose a valid faculty member.")
            return redirect("analytics_chairperson:assignment_reassign", pk=pk)
        old_email = assignment.professor.email
        try:
            assignment = reassign_teaching_assignment(assignment, professor=professor)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("analytics_chairperson:assignment_reassign", pk=pk)
        log_audit_event(
            request.user,
            AuditLog.Action.ASSIGNMENT_CREATE,
            target_user=professor,
            message=(
                f"Reassigned {assignment.subject.code} — "
                f"{assignment.program_section.display_label} from "
                f"{old_email} to {professor.email}"
            ),
            metadata={"from": old_email, "to": professor.email},
        )
        messages.success(
            request,
            f"Reassigned to {professor.get_full_name() or professor.email}.",
        )
        return redirect_preserving_filters(request, "analytics_chairperson:assignments")


class ChairpersonAssignmentSubjectsAPIView(AcademicManagerRequiredMixin, View):
    """GET ?section=<pk>&term=<pk> — subjects for a program section and term."""

    def get(self, request):
        from django.http import JsonResponse

        section_id = request.GET.get("section", "")
        term_id = request.GET.get("term", "")
        if not section_id.isdigit():
            return JsonResponse({"subjects": []})

        section = (
            ProgramSection.objects.filter(pk=int(section_id))
            .select_related("program")
            .first()
        )
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
        return JsonResponse(
            {
                "subjects": [
                    {"id": s.pk, "code": s.code, "name": s.name, "label": str(s)}
                    for s in subjects
                ]
            }
        )


class ChairpersonAssignmentSectionsAPIView(AcademicManagerRequiredMixin, View):
    """GET ?subject=&term= — sections grouped by year with assignment state."""

    def get(self, request):
        subject_id = request.GET.get("subject", "")
        term_id = request.GET.get("term", "")
        if not subject_id.isdigit():
            return JsonResponse({"groups": []})

        subject = (
            Subject.objects.filter(pk=int(subject_id)).select_related("program").first()
        )
        if not subject:
            return JsonResponse({"groups": []})

        dept_id = request.user.department_id
        if dept_id and subject.program.managing_department_id != dept_id:
            return JsonResponse({"groups": []})

        term = (
            AcademicTerm.objects.filter(pk=int(term_id)).first()
            if term_id.isdigit()
            else None
        )
        if not term:
            term = AcademicTerm.get_current()
        if not term:
            return JsonResponse({"groups": []})

        # Match validate_assignment_subject: only sections for this subject's year.
        sections = (
            ProgramSection.queryset_with_counts()
            .filter(
                program=subject.program,
                is_active=True,
                year_level_id=subject.year_level_id,
            )
            .select_related("year_level")
            .order_by("year_level__order", "label")
        )
        assigned_ids = set()
        professor_id = request.GET.get("professor", "")
        if professor_id.isdigit():
            assigned_ids = set(
                TeachingAssignment.objects.filter(
                    subject=subject,
                    term=term,
                    professor_id=int(professor_id),
                ).values_list("program_section_id", flat=True)
            )

        groups: dict[str, dict] = {}
        for section in sections:
            year_name = section.year_level.name if section.year_level else "Other"
            if year_name not in groups:
                groups[year_name] = {"year": year_name, "sections": []}
            groups[year_name]["sections"].append(
                {
                    "id": section.pk,
                    "label": section.display_label,
                    "student_count": section.student_count,
                    "already_assigned": section.pk in assigned_ids,
                }
            )
        return JsonResponse({"groups": list(groups.values())})

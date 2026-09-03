"""Professor course catalog management views."""

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import ProfessorRequiredMixin
from apps.questions.models import Subject, YearLevel
from apps.users.assignment_services import (
    create_catalog_subject,
    delete_catalog_subject,
    get_or_create_catalog_course,
)
from apps.users.forms import FacultySelfServeCourseForm
from apps.users.models import Course, User


class ProfessorCourseListView(ProfessorRequiredMixin, ListView):
    """Table of all BSED Math curriculum subjects (catalog)."""

    model = Subject
    template_name = "professor/courses/list.html"
    context_object_name = "course_cards"

    def get_queryset(self):
        return (
            Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH)
            .select_related("program", "year_level")
            .annotate(question_count=Count("topics__questions", distinct=True))
            .order_by("year_level__order", "semester", "code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cards = []
        for subject in context["course_cards"]:
            catalog_course = get_or_create_catalog_course(self.request.user, subject)
            cards.append(
                {
                    "subject": subject,
                    "catalog_course": catalog_course,
                    "question_count": getattr(subject, "question_count", 0),
                }
            )
        context["course_cards"] = cards
        context["year_levels"] = YearLevel.objects.order_by("order")
        context["semester_choices"] = Subject.Semester.choices
        context["assignments_managed"] = False
        return context


class ProfessorCourseCreateView(ProfessorRequiredMixin, View):
    """Faculty creates a new BSED Math curriculum subject."""

    template_name = "professor/courses/form.html"

    def get(self, request):
        form = FacultySelfServeCourseForm(professor=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = FacultySelfServeCourseForm(request.POST, professor=request.user)
        if form.is_valid():
            try:
                subject, course = create_catalog_subject(
                    code=form.cleaned_data["code"],
                    name=form.cleaned_data["name"],
                    year_level=form.cleaned_data["year_level"],
                    semester=form.cleaned_data["semester"],
                    professor=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, self.template_name, {"form": form})
            messages.success(
                request,
                f"Course {subject.code} — {subject.name} added to the catalog.",
            )
            return redirect("analytics_professor:topic_list", course_pk=course.pk)
        return render(request, self.template_name, {"form": form})


class ProfessorCourseCloneView(ProfessorRequiredMixin, View):
    """Legacy clone endpoint — kept for URL compatibility; redirects to list."""

    def post(self, request, pk):
        messages.info(request, "Cloning offerings is no longer used. Open Courses instead.")
        return redirect("analytics_professor:course_list")


class ProfessorCourseArchiveView(ProfessorRequiredMixin, View):
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk, professor=request.user)
        course.is_archived = True
        course.save(update_fields=["is_archived"])
        messages.success(request, f"{course.code} archived.")
        return redirect("analytics_professor:course_list")


class ProfessorCourseRemoveView(ProfessorRequiredMixin, View):
    """Remove a BSED Math curriculum subject from the catalog."""

    def post(self, request, subject_pk):
        subject = get_object_or_404(
            Subject.objects.select_related("program"),
            pk=subject_pk,
            program__slug=User.HomeDegreeProgram.BSED_MATH,
        )
        code = subject.code
        try:
            delete_catalog_subject(subject)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("analytics_professor:course_list")
        messages.success(request, f"Course subject {code} removed.")
        return redirect("analytics_professor:course_list")

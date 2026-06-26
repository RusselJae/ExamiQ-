from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.ai.factory import get_ai_provider_label, get_calibration_analyzer, get_curriculum_advisor, is_ai_configured
from apps.analytics.services import (
    _course_answers,
    course_performance_summary,
    get_intervention_list,
    get_roster_summaries,
    get_topic_mastery_heatmap,
    professor_overview_summary,
    professor_overview_course_cards,
    student_course_summary,
)
from apps.core.filtering import build_filter_fields, get_filter_param, has_active_filters
from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin
from apps.reviews.models import ReviewSession
from apps.users.models import Course, User


class ProfessorDashboardView(ProfessorRequiredMixin, ListView):
    model = Course
    template_name = "analytics/professor/dashboard.html"
    context_object_name = "courses"

    def get_queryset(self):
        return Course.objects.filter(professor=self.request.user, is_archived=False).select_related("program")


class ProfessorOverviewView(ProfessorRequiredMixin, TemplateView):
    template_name = "analytics/professor/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["overview"] = professor_overview_summary(self.request.user)
        context["course_cards"] = professor_overview_course_cards(self.request.user)
        return context


class CourseDetailView(ProfessorCourseMixin, DetailView):
    model = Course
    template_name = "analytics/professor/course_detail.html"
    context_object_name = "course"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return Course.objects.filter(professor=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = course_performance_summary(self.object)
        context["summary"] = summary
        context["interventions"] = get_intervention_list(self.object)
        context["active_tab"] = "analytics"
        context["ai_enabled"] = is_ai_configured()
        calibration = summary.get("calibration_matrix") or {}
        context["calibration_max"] = max(calibration.values()) if calibration else 1
        return context


class CourseSummaryGenerateView(ProfessorCourseMixin, View):
    """Generate weekly course summary on demand (FAB)."""

    def post(self, request, pk):
        advisor = get_curriculum_advisor()
        narrative = advisor.course_report(self.course)
        return JsonResponse({
            "narrative": narrative,
            "ai_enabled": is_ai_configured(),
        })


class CourseInsightsRedirectView(ProfessorCourseMixin, View):
    """Legacy URL — Insights merged into Analytics."""

    def get(self, request, pk):
        return redirect("analytics_professor:course_detail", pk=self.course.pk)


class CourseRosterView(ProfessorCourseMixin, ListView):
    template_name = "analytics/professor/roster.html"
    context_object_name = "roster"

    def get_queryset(self):
        roster = get_roster_summaries(self.course)

        search = get_filter_param(self.request, "q").lower()
        if search:
            roster = [
                row
                for row in roster
                if search in (row["student"].get_full_name() or "").lower()
                or search in row["student"].email.lower()
            ]

        band = get_filter_param(self.request, "band")
        if band == "struggling":
            roster = [row for row in roster if row["accuracy"] < 50]
        elif band == "developing":
            roster = [row for row in roster if 50 <= row["accuracy"] < 80]
        elif band == "strong":
            roster = [row for row in roster if row["accuracy"] >= 80]

        sort = get_filter_param(self.request, "sort", "name")
        if sort == "accuracy":
            roster = sorted(roster, key=lambda row: row["accuracy"], reverse=True)
        elif sort == "sessions":
            roster = sorted(roster, key=lambda row: row["sessions_completed"], reverse=True)

        return roster

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "roster"
        filter_names = ["q", "band", "sort"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Student name or email",
                },
                {
                    "type": "select",
                    "name": "band",
                    "label": "Performance",
                    "choices": [
                        ("struggling", "Below 50%"),
                        ("developing", "50–79%"),
                        ("strong", "80%+"),
                    ],
                },
                {
                    "type": "select",
                    "name": "sort",
                    "label": "Sort by",
                    "all_label": "Name",
                    "choices": [
                        ("accuracy", "Accuracy"),
                        ("sessions", "Sessions"),
                    ],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class StudentDetailView(ProfessorCourseMixin, DetailView):
    template_name = "analytics/professor/student_detail.html"
    context_object_name = "student"
    pk_url_kwarg = "student_pk"

    def get_object(self):
        student = get_object_or_404(User, pk=self.kwargs["student_pk"], role=User.Role.STUDENT)
        has_sessions = ReviewSession.objects.filter(course=self.course, student=student).exists()
        if not has_sessions:
            from django.http import Http404
            raise Http404("Student has not practiced in this course offering.")
        return student

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = student_course_summary(self.object, self.course)
        answers = _course_answers(self.course, student=self.object)
        calibration = get_calibration_analyzer().analyze(
            self.object,
            answers,
            weak_topics=summary.get("weak_topics"),
        )
        context["summary"] = summary
        context["calibration_narrative"] = calibration["narrative"]
        context["ai_enabled"] = calibration["ai_enabled"]
        context["active_tab"] = "roster"
        return context


class CourseHeatmapView(ProfessorCourseMixin, DetailView):
    model = Course
    template_name = "analytics/professor/heatmap.html"
    context_object_name = "course"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return Course.objects.filter(professor=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heatmap"] = get_topic_mastery_heatmap(self.object)
        context["active_tab"] = "heatmap"
        return context


class CourseInsightsView(ProfessorCourseMixin, DetailView):
    model = Course
    template_name = "analytics/professor/insights.html"
    context_object_name = "course"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return Course.objects.filter(professor=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = course_performance_summary(self.object)
        advisor = get_curriculum_advisor()
        narrative = advisor.course_report(self.object)
        context["summary"] = summary
        context["narrative"] = narrative
        context["ai_enabled"] = is_ai_configured()
        context["ai_provider_label"] = get_ai_provider_label()
        context["active_tab"] = "insights"
        return context


class CourseInterventionsExportView(ProfessorCourseMixin, View):
    """CSV export of intervention flags for a course."""

    def get(self, request, pk):
        import csv
        import hashlib

        from django.http import HttpResponse

        course = self.course
        rows = get_intervention_list(course)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{course.code}_interventions.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "student_id_hash",
                "name",
                "flags",
                "dominant_issue",
                "accuracy",
                "avg_confidence",
                "sessions",
                "suggested_action",
            ]
        )
        for row in rows:
            student = row["student"]
            student_hash = hashlib.sha256(f"examiq-{student.pk}".encode()).hexdigest()[:12]
            writer.writerow(
                [
                    student_hash,
                    student.get_full_name() or student.email,
                    ";".join(row["flags"]),
                    row["dominant_issue"],
                    row["accuracy"],
                    row["avg_confidence"],
                    row["sessions"],
                    row["suggested_action"],
                ]
            )
        return response

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.ai.factory import get_ai_provider_label, get_curriculum_advisor, is_ai_configured
from apps.analytics.services import (
    _course_answers,
    _peer_accuracy_for_answers,
    _section_answers,
    _subject_answers,
    course_performance_summary,
    get_intervention_list,
    get_roster_summaries,
    get_section_heatmap,
    get_section_roster_summaries,
    get_subject_roster_summaries,
    get_topic_mastery_heatmap,
    professor_overview_summary,
    professor_overview_course_cards,
    professor_overview_trends,
    section_heatmap_subjects,
    section_performance_summary,
    student_course_summary,
    student_section_summary,
    student_subject_summary,
    subject_performance_summary,
)
from apps.core.filtering import build_filter_fields, get_filter_param, has_active_filters
from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin
from apps.questions.models import Subject
from apps.reviews.exam_setup_services import get_or_create_section_exam_setup
from apps.reviews.forms_professor import SectionExamSetupForm
from apps.users.assignment_services import get_or_create_catalog_course
from apps.users.models import Course, ProgramSection, User


def _student_initials(student: User) -> str:
    first = (student.first_name or "").strip()
    last = (student.last_name or "").strip()
    if first and last:
        return (first[0] + last[0]).upper()
    name = (student.get_full_name() or student.email or "?").strip()
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper()


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
        context["overview_trends"] = professor_overview_trends(self.request.user)
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
        context["filter_bar_compact"] = True
        return context


class StudentDetailView(ProfessorCourseMixin, DetailView):
    template_name = "analytics/professor/student_detail.html"
    context_object_name = "student"
    pk_url_kwarg = "student_pk"

    def get_object(self):
        # Always allow faculty to open the page; empty metrics when no practice yet.
        return get_object_or_404(
            User, pk=self.kwargs["student_pk"], role=User.Role.STUDENT
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        is_catalog = (self.course.section or "").strip() == "Catalog"
        subject = None
        if is_catalog:
            subject = Subject.objects.filter(
                code=self.course.code, program=self.course.program
            ).first()

        if subject is not None:
            summary = student_subject_summary(self.object, subject)
            peer_answers = _subject_answers(subject)
            peer_accuracy = _peer_accuracy_for_answers(peer_answers)
        else:
            summary = student_course_summary(self.object, self.course)
            peer_answers = _course_answers(self.course)
            peer_accuracy = _peer_accuracy_for_answers(peer_answers)

        context["summary"] = summary
        context["active_tab"] = "roster"
        context["detail_scope"] = "course"

        if summary["accuracy"] < peer_accuracy:
            context["accuracy_subtext"] = "Below class average"
        elif summary["accuracy"] >= 70:
            context["accuracy_subtext"] = "On track"
        else:
            context["accuracy_subtext"] = "Room to improve"

        if summary["avg_confidence"] >= 4 and summary["accuracy"] < 70:
            context["confidence_subtext"] = "High confidence, low accuracy"
        else:
            context["confidence_subtext"] = ""

        last_date = summary.get("last_session_date")
        context["last_session_subtext"] = (
            f"Last session {last_date.strftime('%b %d')}" if last_date else "No sessions yet"
        )
        context["review_hours_subtext"] = (
            "Logged practice time" if summary["review_hours"] else "No review logged yet"
        )
        context["student_initials"] = _student_initials(self.object)
        context["back_url"] = reverse(
            "analytics_professor:course_roster", kwargs={"course_pk": self.course.pk}
        )
        return context


class SectionStudentDetailView(ProfessorRequiredMixin, DetailView):
    """Student detail for a ProgramSection — never 404s for missing practice."""

    template_name = "analytics/professor/section_student_detail.html"
    context_object_name = "student"
    pk_url_kwarg = "student_pk"

    def dispatch(self, request, *args, **kwargs):
        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):
        return get_object_or_404(
            User,
            pk=self.kwargs["student_pk"],
            role=User.Role.STUDENT,
            section=self.section,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = student_section_summary(self.object, self.section)
        peer_answers = _section_answers(self.section)
        peer_accuracy = _peer_accuracy_for_answers(peer_answers)
        context["section"] = self.section
        context["summary"] = summary
        context["active_tab"] = "roster"
        context["detail_scope"] = "section"

        if summary["accuracy"] < peer_accuracy and summary["total_answers"]:
            context["accuracy_subtext"] = "Below section average"
        elif summary["accuracy"] >= 70:
            context["accuracy_subtext"] = "On track"
        elif summary["total_answers"]:
            context["accuracy_subtext"] = "Room to improve"
        else:
            context["accuracy_subtext"] = "No answers yet"

        if summary["avg_confidence"] >= 4 and summary["accuracy"] < 70:
            context["confidence_subtext"] = "High confidence, low accuracy"
        else:
            context["confidence_subtext"] = ""

        last_date = summary.get("last_session_date")
        context["last_session_subtext"] = (
            f"Last session {last_date.strftime('%b %d')}" if last_date else "No sessions yet"
        )
        context["review_hours_subtext"] = (
            "Logged practice time" if summary["review_hours"] else "No review logged yet"
        )
        context["student_initials"] = _student_initials(self.object)
        context["back_url"] = reverse(
            "analytics_professor:section_roster",
            kwargs={"section_pk": self.section.pk},
        )
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


class SectionDetailView(ProfessorRequiredMixin, DetailView):
    """Section-scoped analytics: students in a ProgramSection across subjects."""

    model = ProgramSection
    template_name = "analytics/professor/section_detail.html"
    context_object_name = "section"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return ProgramSection.objects.select_related(
            "program", "year_level", "academic_year"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = section_performance_summary(self.object)
        context["summary"] = summary
        context["active_tab"] = "analytics"
        calibration = summary.get("calibration_matrix") or {}
        context["calibration_max"] = max(calibration.values()) if calibration else 1
        return context


class SectionRosterView(ProfessorRequiredMixin, ListView):
    template_name = "analytics/professor/section_roster.html"
    context_object_name = "roster"

    def dispatch(self, request, *args, **kwargs):
        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        roster = get_section_roster_summaries(self.section)
        search = get_filter_param(self.request, "q").lower()
        if search:
            roster = [
                row
                for row in roster
                if search in (row["student"].get_full_name() or "").lower()
                or search in row["student"].email.lower()
            ]
        return roster

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["active_tab"] = "roster"
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Student name or email",
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, ["q"])
        context["filter_bar_compact"] = True
        return context


class SectionExamSetupView(ProfessorRequiredMixin, View):
    """Faculty configures courses available for a section's exams."""

    template_name = "analytics/professor/section_exam_setup.html"

    def dispatch(self, request, *args, **kwargs):
        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        self.setup = get_or_create_section_exam_setup(self.section)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, section_pk):
        form = SectionExamSetupForm(instance=self.setup)
        return render(
            request,
            self.template_name,
            {
                "section": self.section,
                "form": form,
                "active_tab": "exam_setup",
            },
        )

    def post(self, request, section_pk):
        form = SectionExamSetupForm(request.POST, instance=self.setup)
        if form.is_valid():
            setup = form.save(commit=False)
            setup.section = self.section
            setup.save()
            form.save_m2m()
            from django.contrib import messages

            messages.success(request, f"Exam setup saved for {self.section.display_label}.")
            return redirect("analytics_professor:section_exam_setup", section_pk=self.section.pk)
        return render(
            request,
            self.template_name,
            {
                "section": self.section,
                "form": form,
                "active_tab": "exam_setup",
            },
        )


class SectionHeatmapView(ProfessorRequiredMixin, DetailView):
    model = ProgramSection
    template_name = "analytics/professor/section_heatmap.html"
    context_object_name = "section"
    pk_url_kwarg = "section_pk"

    def get_queryset(self):
        return ProgramSection.objects.select_related("program", "year_level")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subjects = list(section_heatmap_subjects(self.object))
        selected_subject = None
        raw_subject = (self.request.GET.get("subject") or "").strip()
        if raw_subject.isdigit():
            subject_pk = int(raw_subject)
            selected_subject = next((s for s in subjects if s.pk == subject_pk), None)
        if selected_subject is None and subjects:
            selected_subject = subjects[0]

        context["heatmap_subjects"] = subjects
        context["selected_subject"] = selected_subject
        context["heatmap"] = get_section_heatmap(
            self.object, subject=selected_subject
        )
        context["active_tab"] = "heatmap"
        return context


class SectionFeedbackView(ProfessorRequiredMixin, ListView):
    """Student concerns from anyone in this ProgramSection."""

    template_name = "analytics/professor/section_feedback.html"
    context_object_name = "concerns"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        from apps.analytics.concern_services import (
            _concern_activity_filter,
            concern_queryset_with_messages,
        )
        from apps.analytics.models import MistakeRecord

        return concern_queryset_with_messages(
            MistakeRecord.objects.filter(student__section=self.section)
            .filter(_concern_activity_filter())
            .select_related(
                "student",
                "question",
                "topic",
                "answer",
                "question__topic",
                "question__topic__subject",
            )
            .order_by("-occurred_at")
        )

    def get_context_data(self, **kwargs):
        from apps.analytics.concern_services import pending_concern_count_for_section
        from apps.reviews.views_professor_feedback import _concern_item_payload

        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["active_tab"] = "feedback"
        context["concern_items"] = [
            _concern_item_payload(record) for record in context["concerns"]
        ]
        context["pending_concern_count"] = pending_concern_count_for_section(
            self.section
        )
        return context


class SubjectDetailView(ProfessorRequiredMixin, DetailView):
    """Catalog subject analytics across all year levels."""

    model = Subject
    template_name = "analytics/professor/subject_detail.html"
    context_object_name = "subject"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        return Subject.objects.filter(
            program__slug=User.HomeDegreeProgram.BSED_MATH
        ).select_related("program", "year_level")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = subject_performance_summary(self.object)
        context["summary"] = summary
        context["active_tab"] = "analytics"
        calibration = summary.get("calibration_matrix") or {}
        context["calibration_max"] = max(calibration.values()) if calibration else 1
        context["catalog_course"] = get_or_create_catalog_course(
            self.request.user, self.object
        )
        return context


class SubjectRosterView(ProfessorRequiredMixin, ListView):
    template_name = "analytics/professor/subject_roster.html"
    context_object_name = "roster"

    def dispatch(self, request, *args, **kwargs):
        self.subject = get_object_or_404(
            Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH),
            pk=kwargs["subject_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        roster = get_subject_roster_summaries(self.subject)
        search = get_filter_param(self.request, "q").lower()
        if search:
            roster = [
                row
                for row in roster
                if search in (row["student"].get_full_name() or "").lower()
                or search in row["student"].email.lower()
            ]
        return roster

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["subject"] = self.subject
        context["active_tab"] = "roster"
        context["catalog_course"] = get_or_create_catalog_course(
            self.request.user, self.subject
        )
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Student name or email",
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, ["q"])
        context["filter_bar_compact"] = True
        return context

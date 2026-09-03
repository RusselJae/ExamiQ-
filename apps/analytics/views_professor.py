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
    get_professor_students_with_exams,
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
    student_professor_summary,
    student_section_summary,
    student_subject_summary,
    subject_performance_summary,
)
from apps.core.filtering import (
    build_filter_fields,
    get_filter_param,
    has_active_filters,
    redirect_preserving_filters,
)
from apps.core.mixins import (
    FacultyLegacyRosterBlockedMixin,
    ProfessorCourseMixin,
    ProfessorRequiredMixin,
)
from apps.questions.models import Subject
from apps.reviews.exam_setup_services import (
    get_or_create_program_exam_setup,
    program_subject_timer_rows,
    subject_exam_timer_seconds,
)
from apps.reviews.models import Answer, ReviewSession
from apps.users.assignment_services import (
    archive_section_student,
    faculty_can_manage_section_student,
    get_faculty_profile_section_ids,
    get_or_create_catalog_course,
    professor_can_view_session,
    professor_can_view_student,
    restore_section_student,
)
from apps.users.models import Course, Program, ProgramSection, User


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


class ExamSetupHubView(ProfessorRequiredMixin, View):
    """Program-wide exam setup for all BSED Math students."""

    template_name = "analytics/professor/program_exam_setup.html"

    def dispatch(self, request, *args, **kwargs):
        program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
        if program is None:
            from django.contrib import messages

            messages.error(request, "BSED Math program is not configured.")
            return redirect("analytics_professor:overview")
        self.program = program
        self.setup = get_or_create_program_exam_setup(program)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        subject_rows = program_subject_timer_rows(self.program)
        configured_rows = [row for row in subject_rows if row["selected"]]
        return render(
            request,
            self.template_name,
            {
                "program": self.program,
                "setup": self.setup,
                "subject_rows": subject_rows,
                "configured_rows": configured_rows,
                "default_seconds": self.setup.seconds_per_question or 30,
            },
        )

    def post(self, request):
        from apps.reviews.exam_setup_services import sync_program_subject_timers

        default_raw = request.POST.get("default_seconds", "")
        try:
            default_seconds = int(default_raw) if default_raw else self.setup.seconds_per_question
        except (TypeError, ValueError):
            default_seconds = self.setup.seconds_per_question or 30
        if not 10 <= default_seconds <= 120:
            from django.contrib import messages

            messages.error(request, "Default timer must be between 10 and 120 seconds.")
            return self.get(request)

        subject_ids = [
            int(value)
            for value in request.POST.getlist("subjects")
            if str(value).isdigit()
        ]
        timers: dict[int, int] = {}
        for subject_id in subject_ids:
            raw = request.POST.get(f"timer_{subject_id}", "").strip()
            try:
                timers[subject_id] = int(raw) if raw else default_seconds
            except ValueError:
                timers[subject_id] = default_seconds

        try:
            sync_program_subject_timers(
                self.program,
                subject_ids=subject_ids,
                timers_by_subject_id=timers,
                default_seconds=default_seconds,
            )
        except ValueError as exc:
            from django.contrib import messages

            messages.error(request, str(exc))
            return self.get(request)

        from django.contrib import messages

        messages.success(request, "Exam setup saved for all BSED Math students.")
        return redirect("analytics_professor:exam_setup_hub")


class ProfessorStudentsView(ProfessorRequiredMixin, ListView):
    """Students who completed exams on this professor's courses."""

    template_name = "analytics/professor/students.html"
    context_object_name = "roster"

    def get_queryset(self):
        show_archived = get_filter_param(self.request, "show_archived") == "1"
        roster = get_professor_students_with_exams(
            self.request.user, include_archived=show_archived
        )
        section_ids = get_faculty_profile_section_ids(self.request.user)

        search = get_filter_param(self.request, "q").lower()
        if search:
            roster = [
                row
                for row in roster
                if search in (row["student"].get_full_name() or "").lower()
                or search in row["student"].email.lower()
            ]

        sort = get_filter_param(self.request, "sort", "name")
        if sort == "sessions":
            roster = sorted(
                roster, key=lambda row: row["sessions_completed"], reverse=True
            )
        elif sort == "recent":
            roster = sorted(
                roster,
                key=lambda row: row["last_activity"] or row["student"].date_joined,
                reverse=True,
            )

        for row in roster:
            student = row["student"]
            row["can_manage"] = bool(
                student.section_id and student.section_id in section_ids
            )

        return roster

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_names = ["q", "sort", "show_archived"]
        context["show_archived"] = get_filter_param(self.request, "show_archived") == "1"
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
                    "name": "sort",
                    "label": "Sort by",
                    "all_label": "Name",
                    "choices": [
                        ("sessions", "Sessions"),
                        ("recent", "Recent activity"),
                    ],
                },
                {
                    "type": "select",
                    "name": "show_archived",
                    "label": "Archived",
                    "all_label": "Hide archived",
                    "choices": [("1", "Show archived")],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        context["filter_bar_compact"] = True
        return context


class ProfessorStudentDetailView(ProfessorRequiredMixin, DetailView):
    """Student detail across all of this professor's courses."""

    template_name = "analytics/professor/professor_student_detail.html"
    context_object_name = "student"
    pk_url_kwarg = "student_pk"

    def get_object(self):
        student = get_object_or_404(
            User, pk=self.kwargs["student_pk"], role=User.Role.STUDENT
        )
        if not professor_can_view_student(self.request.user, student):
            from django.http import Http404

            raise Http404(
                "Student has no completed exams in your assigned courses or subjects."
            )
        return student

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        professor = self.request.user
        summary = student_professor_summary(self.object, professor)
        peer_answers = Answer.objects.filter(session__course__professor=professor)
        peer_accuracy = _peer_accuracy_for_answers(peer_answers)

        context["summary"] = summary
        context["detail_scope"] = "professor"

        if summary["accuracy"] < peer_accuracy and summary["total_answers"]:
            context["accuracy_subtext"] = "Below class average"
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
        context["back_url"] = reverse("analytics_professor:students")
        context["scope_label"] = "Your courses"
        return context


class ProfessorSessionReviewView(ProfessorRequiredMixin, DetailView):
    """Read-only session summary for faculty reviewing a student's exam."""

    model = ReviewSession
    template_name = "analytics/professor/session_review.html"
    context_object_name = "session"
    pk_url_kwarg = "session_pk"

    def get_queryset(self):
        return ReviewSession.objects.filter(
            student_id=self.kwargs["student_pk"],
            status__in=[
                ReviewSession.Status.COMPLETED,
                ReviewSession.Status.EXPIRED,
            ],
        ).select_related("student", "topic", "topic__subject", "course")

    def get_object(self, queryset=None):
        session = super().get_object(queryset)
        if not professor_can_view_session(self.request.user, session):
            from django.http import Http404

            raise Http404()
        return session

    def get_context_data(self, **kwargs):
        import math

        from apps.reviews.recommendations import build_session_summary

        context = super().get_context_data(**kwargs)
        session = self.object
        session_summary = build_session_summary(session)
        incorrect = max(
            0,
            session_summary["total_questions"] - session_summary["correct_count"],
        )
        circumference = 2 * math.pi * 42
        fraction = (session_summary["accuracy"] or 0) / 100
        context["student"] = session.student
        context["session_summary"] = session_summary
        context["incorrect_count"] = incorrect
        context["score_ring_dasharray"] = f"{circumference:.2f}"
        context["score_ring_dashoffset"] = f"{circumference * (1 - fraction):.2f}"
        context["student_initials"] = _student_initials(session.student)
        context["back_url"] = reverse(
            "analytics_professor:professor_student_detail",
            kwargs={"student_pk": session.student_id},
        )
        context["back_label"] = "Back to student"
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


class CourseRosterView(FacultyLegacyRosterBlockedMixin, ProfessorCourseMixin, ListView):
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


class StudentDetailView(FacultyLegacyRosterBlockedMixin, ProfessorCourseMixin, DetailView):
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


class SectionStudentDetailView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, DetailView):
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


class SectionDetailView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, DetailView):
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


class SectionRosterView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, ListView):
    template_name = "analytics/professor/section_roster.html"
    context_object_name = "roster"

    def dispatch(self, request, *args, **kwargs):
        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        show_archived = get_filter_param(self.request, "show_archived") == "1"
        roster = get_section_roster_summaries(
            self.section, include_archived=show_archived
        )
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
        context["show_archived"] = get_filter_param(self.request, "show_archived") == "1"
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
                    "name": "show_archived",
                    "label": "Archived",
                    "all_label": "Hide archived",
                    "choices": [("1", "Show archived")],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(
            self.request, ["q", "show_archived"]
        )
        context["filter_bar_compact"] = True
        return context


class SectionStudentArchiveView(ProfessorRequiredMixin, View):
    def post(self, request, section_pk, student_pk):
        section = get_object_or_404(ProgramSection, pk=section_pk)
        student = get_object_or_404(User, pk=student_pk, role=User.Role.STUDENT)
        if not faculty_can_manage_section_student(request.user, section, student):
            from django.http import Http404

            raise Http404()

        from django.contrib import messages

        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        archive_section_student(request.user, section, student)
        log_audit_event(
            request.user,
            AuditLog.Action.USER_ARCHIVE,
            target_user=student,
            message=f"Archived student {student.email} from {section.display_label}",
            target_type="User",
            target_id=student.pk,
        )
        messages.success(
            request,
            f"{student.get_full_name() or student.email} has been archived.",
        )
        return redirect_preserving_filters(
            request,
            "analytics_professor:students",
        )


class SectionStudentRestoreView(ProfessorRequiredMixin, View):
    def post(self, request, section_pk, student_pk):
        section = get_object_or_404(ProgramSection, pk=section_pk)
        student = get_object_or_404(User, pk=student_pk, role=User.Role.STUDENT)
        if not faculty_can_manage_section_student(request.user, section, student):
            from django.http import Http404

            raise Http404()

        from django.contrib import messages

        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        restore_section_student(request.user, section, student)
        log_audit_event(
            request.user,
            AuditLog.Action.USER_RESTORE,
            target_user=student,
            message=f"Restored student {student.email} in {section.display_label}",
            target_type="User",
            target_id=student.pk,
        )
        messages.success(
            request,
            f"{student.get_full_name() or student.email} has been restored.",
        )
        return redirect_preserving_filters(
            request,
            "analytics_professor:students",
        )


class SectionExamSetupRedirectView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, View):
    """Legacy per-section exam setup URLs redirect to program-wide setup."""

    def get(self, request, section_pk):
        return redirect("analytics_professor:exam_setup_hub")

    def post(self, request, section_pk):
        return redirect("analytics_professor:exam_setup_hub")


class SectionHeatmapView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, DetailView):
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


class SectionFeedbackView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, ListView):
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


class SubjectDetailView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, DetailView):
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
        context["exam_timer_seconds"] = subject_exam_timer_seconds(self.object)
        return context


class SubjectRosterView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, ListView):
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

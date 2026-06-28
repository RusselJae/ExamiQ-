"""In-app campus administration."""

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView

from apps.core.mixins import CampusAdminRequiredMixin
from apps.users.email_services import send_account_approved_email, send_account_rejected_email
from apps.users.forms import (
    AcademicTermForm,
    AcademicYearForm,
    CampusChairpersonCreateForm,
    CampusProfessorCreateForm,
    ProgramSectionBulkForm,
    ProgramSectionForm,
)
from apps.users.models import AcademicTerm, AcademicYear, Program, ProgramSection, User
from apps.users.notification_services import create_notification
from apps.users.section_services import get_current_academic_year


def _campus_recent_activity(limit: int = 8) -> list[dict]:
    """Build a lightweight activity feed for the campus dashboard."""
    activities: list[dict] = []

    for user in (
        User.objects.filter(role__in=[User.Role.PROFESSOR, User.Role.CHAIRPERSON])
        .order_by("-date_joined")[:6]
    ):
        name = user.get_full_name() or user.email
        role_label = user.get_role_display().lower()
        activities.append(
            {
                "message": f"New {role_label} account provisioned — {name}",
                "timestamp": user.date_joined,
                "tone": "success",
            }
        )

    for user in User.objects.filter(approval_status=User.ApprovalStatus.PENDING).order_by(
        "-date_joined"
    )[:4]:
        name = user.get_full_name() or user.email
        activities.append(
            {
                "message": f"New registration awaiting approval — {name}",
                "timestamp": user.date_joined,
                "tone": "warning",
            }
        )

    for user in (
        User.objects.filter(role=User.Role.STUDENT, is_active=False)
        .exclude(approval_status=User.ApprovalStatus.PENDING)
        .order_by("-date_joined")[:3]
    ):
        name = user.get_full_name() or user.email
        activities.append(
            {
                "message": f"Student account deactivated — {name}",
                "timestamp": user.date_joined,
                "tone": "error",
            }
        )

    activities.sort(key=lambda row: row["timestamp"], reverse=True)
    return activities[:limit]


class CampusDashboardView(CampusAdminRequiredMixin, TemplateView):
    template_name = "campus/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month_ago = timezone.now() - timedelta(days=30)
        students = User.objects.filter(role=User.Role.STUDENT)
        professors = User.objects.filter(role=User.Role.PROFESSOR)
        chairpersons = User.objects.filter(role=User.Role.CHAIRPERSON)
        context["student_count"] = students.count()
        context["professor_count"] = professors.count()
        context["chairperson_count"] = chairpersons.count()
        context["new_students_count"] = students.filter(date_joined__gte=month_ago).count()
        context["student_subtext"] = (
            f"+{context['new_students_count']} this month"
            if context["new_students_count"]
            else "No new students this month"
        )
        context["active_professor_count"] = professors.filter(is_active=True).count()
        context["professor_subtext"] = f"{context['active_professor_count']} active accounts"
        context["active_chairperson_count"] = chairpersons.filter(is_active=True).count()
        context["chairperson_subtext"] = f"{context['active_chairperson_count']} active"
        context["pending_count"] = User.objects.filter(
            approval_status=User.ApprovalStatus.PENDING
        ).count()
        sections = ProgramSection.queryset_with_counts().filter(is_active=True)
        context["section_count"] = sections.count()
        context["sections_near_capacity"] = [
            s for s in sections if s.remaining_slots <= 5 and not s.is_full
        ]
        context["sections_full"] = [s for s in sections if s.is_full]
        context["current_academic_year"] = get_current_academic_year()
        context["current_term"] = AcademicTerm.get_current()
        context["recent_activity"] = _campus_recent_activity()
        return context


class CampusUserListView(CampusAdminRequiredMixin, ListView):
    template_name = "campus/users/list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.select_related("department", "year_level", "section").order_by("email")
        role = self.request.GET.get("role", "")
        if role in {choice[0] for choice in User.Role.choices}:
            qs = qs.filter(role=role)
        status = self.request.GET.get("status", "")
        if status in {
            User.ApprovalStatus.PENDING,
            User.ApprovalStatus.APPROVED,
            User.ApprovalStatus.REJECTED,
        }:
            qs = qs.filter(approval_status=status)
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(student_number__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_filter"] = self.request.GET.get("role", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["role_choices"] = User.Role.choices
        context["status_choices"] = User.ApprovalStatus.choices
        return context


class CampusCreateProfessorView(CampusAdminRequiredMixin, FormView):
    template_name = "campus/users/create_professor.html"
    form_class = CampusProfessorCreateForm
    success_url = reverse_lazy("campus:user_list")

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f"Faculty account created for {user.email}.")
        return super().form_valid(form)


class CampusCreateChairpersonView(CampusAdminRequiredMixin, FormView):
    template_name = "campus/users/create_chairperson.html"
    form_class = CampusChairpersonCreateForm
    success_url = reverse_lazy("campus:user_list")

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f"Chairperson account created for {user.email}.")
        return super().form_valid(form)


class CampusToggleUserActiveView(CampusAdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user == request.user:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect("campus:user_list")

        if user.approval_status == User.ApprovalStatus.PENDING:
            messages.error(request, "Use Accept or Reject for pending registrations.")
            return redirect("campus:user_list")

        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "activated" if user.is_active else "deactivated"
        messages.success(request, f"{user.email} has been {state}.")
        return redirect("campus:user_list")


class CampusApproveUserView(CampusAdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.approval_status != User.ApprovalStatus.PENDING:
            messages.error(request, "Only pending registrations can be approved.")
            return redirect("campus:user_list")

        user.is_active = True
        user.approval_status = User.ApprovalStatus.APPROVED
        user.save(update_fields=["is_active", "approval_status"])
        send_account_approved_email(user)
        create_notification(
            user,
            "Your EXAMIQ+ account has been approved. You can now sign in.",
            link="/accounts/login/",
        )
        messages.success(request, f"{user.email} has been approved.")
        return redirect("campus:user_list")


class CampusRejectUserView(CampusAdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.approval_status != User.ApprovalStatus.PENDING:
            messages.error(request, "Only pending registrations can be rejected.")
            return redirect("campus:user_list")

        user.is_active = False
        user.approval_status = User.ApprovalStatus.REJECTED
        user.save(update_fields=["is_active", "approval_status"])
        send_account_rejected_email(user)
        create_notification(
            user,
            "Your EXAMIQ+ registration was not approved.",
            link="/accounts/login/?registered=rejected",
        )
        messages.success(request, f"{user.email} has been rejected.")
        return redirect("campus:user_list")


class CampusSectionListView(CampusAdminRequiredMixin, ListView):
    template_name = "campus/sections/list.html"
    context_object_name = "sections"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            ProgramSection.queryset_with_counts()
            .select_related("program", "year_level", "academic_year")
            .order_by("program__name", "year_level__order", "label")
        )
        program_id = self.request.GET.get("program", "")
        if program_id.isdigit():
            qs = qs.filter(program_id=int(program_id))
        year_level_id = self.request.GET.get("year_level", "")
        if year_level_id.isdigit():
            qs = qs.filter(year_level_id=int(year_level_id))
        academic_year_id = self.request.GET.get("academic_year", "")
        if academic_year_id.isdigit():
            qs = qs.filter(academic_year_id=int(academic_year_id))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["programs"] = Program.objects.all().order_by("name")
        context["academic_years"] = AcademicYear.objects.all().order_by("-label")
        context["program_filter"] = self.request.GET.get("program", "")
        context["year_level_filter"] = self.request.GET.get("year_level", "")
        context["academic_year_filter"] = self.request.GET.get("academic_year", "")
        return context


class CampusSectionCreateView(CampusAdminRequiredMixin, CreateView):
    model = ProgramSection
    form_class = ProgramSectionForm
    template_name = "campus/sections/form.html"
    success_url = reverse_lazy("campus:section_list")

    def form_valid(self, form):
        messages.success(self.request, "Section created.")
        return super().form_valid(form)


class CampusSectionUpdateView(CampusAdminRequiredMixin, UpdateView):
    model = ProgramSection
    form_class = ProgramSectionForm
    template_name = "campus/sections/form.html"
    success_url = reverse_lazy("campus:section_list")

    def form_valid(self, form):
        messages.success(self.request, "Section updated.")
        return super().form_valid(form)


class CampusSectionBulkCreateView(CampusAdminRequiredMixin, FormView):
    template_name = "campus/sections/bulk_form.html"
    form_class = ProgramSectionBulkForm
    success_url = reverse_lazy("campus:section_list")

    def form_valid(self, form):
        created = form.save()
        messages.success(self.request, f"Created {len(created)} section(s).")
        return super().form_valid(form)


class CampusAcademicCalendarView(CampusAdminRequiredMixin, TemplateView):
    template_name = "campus/academic_calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        academic_years = (
            AcademicYear.objects.annotate(term_total=Count("terms"))
            .prefetch_related(
                Prefetch("terms", queryset=AcademicTerm.objects.order_by("name"))
            )
            .order_by("-label")
        )
        context["academic_years"] = academic_years
        context["calendar_stats"] = {
            "year_count": academic_years.count(),
            "term_count": AcademicTerm.objects.count(),
            "current_year": get_current_academic_year(),
            "current_term": AcademicTerm.get_current(),
        }
        context["year_form"] = kwargs.get("year_form", AcademicYearForm())
        context["term_form"] = kwargs.get("term_form", AcademicTermForm())
        context["prefill_year_id"] = self.request.GET.get("year", "")
        return context

    def post(self, request):
        action = request.POST.get("action")
        if action == "create_year":
            form = AcademicYearForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Academic year saved.")
                return redirect("campus:academic_calendar")
            return self.render_to_response(self.get_context_data(year_form=form))

        if action == "create_term":
            form = AcademicTermForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Academic term saved.")
                return redirect("campus:academic_calendar")
            return self.render_to_response(self.get_context_data(term_form=form))

        if action == "set_current_year":
            year = get_object_or_404(AcademicYear, pk=request.POST.get("year_id"))
            year.is_current = True
            year.save()
            messages.success(request, f"{year.label} is now the current academic year.")
            return redirect("campus:academic_calendar")

        if action == "set_current_term":
            term = get_object_or_404(
                AcademicTerm.objects.select_related("academic_year"),
                pk=request.POST.get("term_id"),
            )
            term.is_current = True
            term.save()
            messages.success(request, f"{term.name} is now the current term.")
            return redirect("campus:academic_calendar")

        return redirect("campus:academic_calendar")

"""Chairperson department-management views (accounts and subjects)."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, UpdateView

from apps.core.filtering import redirect_preserving_filters
from apps.core.mixins import ChairpersonRequiredMixin
from apps.questions.models import Subject
from apps.users.assignment_services import (
    create_curriculum_subject,
    delete_curriculum_subject,
)
from apps.users.email_services import (
    send_account_approved_email,
    send_account_rejected_email,
)
from apps.users.forms import ChairpersonSubjectForm, ProgramCoordinatorSubjectForm
from apps.users.models import Program, User
from apps.users.notification_services import create_notification


def _managed_programs(user: User):
    """Programs managed by the chairperson's department (all when unassigned)."""
    programs = Program.objects.all()
    if user.department_id:
        return programs.filter(managing_department=user.department)
    return programs


def _managed_faculty(user: User):
    """Faculty accounts (including pending requests) in the department."""
    if not user.department_id:
        return User.objects.filter(role=User.Role.PROFESSOR)
    return User.objects.filter(role=User.Role.PROFESSOR, department=user.department)


def _managed_users(user: User):
    """All manageable accounts in the department: faculty plus students."""
    if not user.department_id:
        return User.objects.filter(role__in=[User.Role.PROFESSOR, User.Role.STUDENT])
    from apps.users.constants import students_in_department

    return User.objects.filter(
        Q(pk__in=_managed_faculty(user))
        | Q(pk__in=students_in_department(user.department))
    )


class ChairpersonAccountListView(ChairpersonRequiredMixin, ListView):
    """Approve and manage user accounts in the department."""

    template_name = "chairperson/accounts/list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = _managed_users(self.request.user).select_related(
            "department", "year_level", "section"
        )
        role = self.request.GET.get("role", "")
        if role in {User.Role.STUDENT, User.Role.PROFESSOR}:
            qs = qs.filter(role=role)
        active = self.request.GET.get("active", "")
        if active == "active":
            qs = qs.filter(is_active=True, approval_status=User.ApprovalStatus.APPROVED)
        elif active == "inactive":
            qs = qs.exclude(
                is_active=True, approval_status=User.ApprovalStatus.APPROVED
            )
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
                | Q(employee_id__icontains=search)
                | Q(student_number__icontains=search)
            )
        return qs.order_by("-date_joined")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_filter"] = self.request.GET.get("role", "")
        context["active_filter"] = self.request.GET.get("active", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["role_choices"] = [
            (User.Role.STUDENT, "Student"),
            (User.Role.PROFESSOR, "Faculty"),
        ]
        context["status_choices"] = User.ApprovalStatus.choices
        context["pending_count"] = (
            _managed_faculty(self.request.user)
            .filter(approval_status=User.ApprovalStatus.PENDING)
            .count()
        )
        return context


class ChairpersonApproveUserView(ChairpersonRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(_managed_users(request.user), pk=pk)
        if user.approval_status != User.ApprovalStatus.PENDING:
            messages.error(request, "Only pending registrations can be approved.")
            return redirect_preserving_filters(
                request, "analytics_chairperson:accounts"
            )

        user.is_active = True
        user.approval_status = User.ApprovalStatus.APPROVED
        user.save(update_fields=["is_active", "approval_status"])
        send_account_approved_email(user)
        create_notification(
            user,
            "Your EXAMIQ+ faculty account has been approved. You can now sign in.",
            link="/accounts/login/",
        )
        messages.success(request, f"{user.email} has been approved.")
        return redirect_preserving_filters(request, "analytics_chairperson:accounts")


class ChairpersonRejectUserView(ChairpersonRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(_managed_users(request.user), pk=pk)
        if user.approval_status != User.ApprovalStatus.PENDING:
            messages.error(request, "Only pending registrations can be rejected.")
            return redirect_preserving_filters(
                request, "analytics_chairperson:accounts"
            )

        user.is_active = False
        user.approval_status = User.ApprovalStatus.REJECTED
        user.save(update_fields=["is_active", "approval_status"])
        send_account_rejected_email(user)
        messages.success(request, f"{user.email} has been rejected.")
        return redirect_preserving_filters(request, "analytics_chairperson:accounts")


class ChairpersonToggleUserActiveView(ChairpersonRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(_managed_users(request.user), pk=pk)
        if user.approval_status == User.ApprovalStatus.PENDING:
            messages.error(request, "Use Accept or Reject for pending registrations.")
            return redirect_preserving_filters(
                request, "analytics_chairperson:accounts"
            )

        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "activated" if user.is_active else "deactivated"
        messages.success(request, f"{user.email} has been {state}.")
        return redirect_preserving_filters(request, "analytics_chairperson:accounts")


class ChairpersonSubjectListView(ChairpersonRequiredMixin, ListView):
    """List and add curriculum subjects for managed programs."""

    template_name = "chairperson/subjects/list.html"
    context_object_name = "subjects"
    paginate_by = 25

    def get_queryset(self):
        return (
            Subject.objects.filter(program__in=_managed_programs(self.request.user))
            .select_related("program", "year_level")
            .order_by("program__name", "year_level__order", "semester", "code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get(
            "form",
            ProgramCoordinatorSubjectForm(coordinator=self.request.user),
        )
        return context

    def post(self, request, *args, **kwargs):
        form = ProgramCoordinatorSubjectForm(request.POST, coordinator=request.user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        subject = create_curriculum_subject(
            program=form.cleaned_data["program"],
            code=form.cleaned_data["code"],
            name=form.cleaned_data["name"],
            year_level=form.cleaned_data["year_level"],
            semester=form.cleaned_data["semester"],
        )
        messages.success(
            request,
            f"{subject.code} — {subject.name} was added to the course catalog.",
        )
        return redirect("analytics_chairperson:subjects")


class ChairpersonSubjectUpdateView(ChairpersonRequiredMixin, UpdateView):
    model = Subject
    form_class = ChairpersonSubjectForm
    template_name = "chairperson/subjects/form.html"
    success_url = reverse_lazy("analytics_chairperson:subjects")

    def get_queryset(self):
        return Subject.objects.filter(program__in=_managed_programs(self.request.user))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["manager"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"{form.instance.code} updated.")
        return super().form_valid(form)


class ChairpersonSubjectDeleteView(ChairpersonRequiredMixin, View):
    def post(self, request, pk):
        subject = get_object_or_404(
            Subject.objects.filter(program__in=_managed_programs(request.user)),
            pk=pk,
        )
        code = delete_curriculum_subject(subject)
        messages.success(request, f"{code} removed from the course catalog.")
        return redirect("analytics_chairperson:subjects")

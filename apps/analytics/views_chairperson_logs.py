"""Chairperson audit log views."""

from django.db.models import Q

from django.views.generic import ListView

from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
)
from apps.core.mixins import ChairpersonRequiredMixin
from apps.core.models import AuditLog
from apps.users.constants import home_programs_for_department
from apps.users.models import User


class _BaseAuditLogView(ChairpersonRequiredMixin, ListView):
    model = AuditLog
    template_name = "analytics/chairperson/audit_logs.html"
    context_object_name = "logs"
    paginate_by = 30
    role_filter: str = ""

    def _department_user_ids(self):
        department = self.request.user.department
        if not department:
            return User.objects.none().values_list("pk", flat=True)
        dept_slugs = set(home_programs_for_department(department))
        qs = User.objects.filter(role=self.role_filter)
        if dept_slugs:
            qs = qs.filter(
                Q(home_program__in=dept_slugs)
                | Q(department=department)
                | Q(role=User.Role.PROFESSOR, teaching_assignments__program_section__program__managing_department=department)
            )
        else:
            qs = qs.filter(department=department)
        return qs.distinct().values_list("pk", flat=True)

    def get_queryset(self):
        user_ids = list(self._department_user_ids())
        qs = AuditLog.objects.filter(
            Q(actor_id__in=user_ids) | Q(target_user_id__in=user_ids)
        ).select_related("actor", "target_user")
        qs = apply_date_range(qs, self.request, "created_at")
        qs = apply_sort(
            qs,
            self.request,
            newest_field="-created_at",
            oldest_field="created_at",
        )
        search = get_filter_param(self.request, "q")
        if search:
            qs = qs.filter(
                Q(message__icontains=search)
                | Q(actor__email__icontains=search)
                | Q(target_user__email__icontains=search)
            )
        action = get_filter_param(self.request, "action")
        if action in dict(AuditLog.Action.choices):
            qs = qs.filter(action=action)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["log_title"] = self.log_title
        context["filter_bar_compact"] = True
        filter_names = ["q", "action", "date_from", "date_to", "sort"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Message or email",
                },
                {
                    "type": "select",
                    "name": "action",
                    "label": "Action",
                    "choices": AuditLog.Action.choices,
                },
                *STANDARD_DATE_SORT_FILTER_SPECS,
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class FacultyAuditLogView(_BaseAuditLogView):
    log_title = "Faculty activity"
    role_filter = User.Role.PROFESSOR


class StudentAuditLogView(_BaseAuditLogView):
    log_title = "Student activity"
    role_filter = User.Role.STUDENT

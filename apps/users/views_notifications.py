"""In-app notification views."""

from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    has_active_filters,
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from apps.users.models import Notification
from apps.users.notification_services import mark_notifications_read, unread_notification_count


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "users/notifications.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)
        queryset = apply_date_range(queryset, self.request, "created_at")
        return apply_sort(
            queryset,
            self.request,
            newest_field="-created_at",
            oldest_field="created_at",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_names = ["date_from", "date_to", "sort"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            STANDARD_DATE_SORT_FILTER_SPECS,
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        context["filter_bar_compact"] = True
        return context


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request):
        notification_ids = request.POST.getlist("ids")
        ids = [int(pk) for pk in notification_ids if str(pk).isdigit()]
        mark_notifications_read(request.user, ids or None)
        next_url = request.POST.get("next", "")
        if next_url:
            return redirect(next_url)
        return redirect("users:notifications")


class NotificationUnreadCountAPIView(LoginRequiredMixin, View):
    def get(self, request):
        return JsonResponse({"count": unread_notification_count(request.user)})

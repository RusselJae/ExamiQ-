"""In-app notification views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.analytics.concern_services import mark_concern_notifications_read
from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    has_active_filters,
)
from apps.users.models import Notification
from apps.users.notification_services import mark_notifications_read, unread_notification_count


def _safe_relative_link(link: str) -> str:
    """Allow only same-origin relative paths (no scheme-relative URLs)."""
    if not link or not link.startswith("/") or link.startswith("//"):
        return reverse("users:notifications")
    return link


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
        from apps.users.notification_services import notification_cta_label

        for notification in context["notifications"]:
            notification.cta_label = notification_cta_label(notification)
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


class NotificationOpenView(LoginRequiredMixin, View):
    """Mark one notification read, then redirect to its relative link."""

    def get(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.mark_read()
        return redirect(_safe_relative_link(notification.link or ""))


class NotificationMarkLinkView(LoginRequiredMixin, View):
    """Mark unread notifications whose link matches answer_id or mistake_id."""

    def post(self, request):
        answer_id = request.POST.get("answer_id")
        mistake_id = request.POST.get("mistake_id")
        if answer_id and str(answer_id).isdigit():
            mark_concern_notifications_read(request.user, answer_id=int(answer_id))
        elif mistake_id and str(mistake_id).isdigit():
            mark_concern_notifications_read(request.user, int(mistake_id))
        return JsonResponse({"ok": True})


class NotificationUnreadCountAPIView(LoginRequiredMixin, View):
    def get(self, request):
        return JsonResponse({"count": unread_notification_count(request.user)})

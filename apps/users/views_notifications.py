"""In-app notification views."""

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
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


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

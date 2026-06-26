"""In-app campus administration for Django superusers."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from apps.core.mixins import CampusAdminRequiredMixin
from apps.users.forms import CampusChairpersonCreateForm, CampusProfessorCreateForm
from apps.users.models import User


class CampusDashboardView(CampusAdminRequiredMixin, TemplateView):
    template_name = "campus/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student_count"] = User.objects.filter(role=User.Role.STUDENT).count()
        context["professor_count"] = User.objects.filter(role=User.Role.PROFESSOR).count()
        context["chairperson_count"] = User.objects.filter(role=User.Role.CHAIRPERSON).count()
        return context


class CampusUserListView(CampusAdminRequiredMixin, ListView):
    template_name = "campus/users/list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.select_related("department").order_by("email")
        role = self.request.GET.get("role", "")
        if role in {User.Role.STUDENT, User.Role.PROFESSOR, User.Role.CHAIRPERSON}:
            qs = qs.filter(role=role)
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_filter"] = self.request.GET.get("role", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["role_choices"] = User.Role.choices
        return context


class CampusCreateProfessorView(CampusAdminRequiredMixin, FormView):
    template_name = "campus/users/create_professor.html"
    form_class = CampusProfessorCreateForm
    success_url = reverse_lazy("campus:user_list")

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f"Professor account created for {user.email}.")
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

        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "activated" if user.is_active else "deactivated"
        messages.success(request, f"{user.email} has been {state}.")
        return redirect("campus:user_list")

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import ProfessorCourseMixin
from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.reviews.forms_professor import ExamSetupForm, ReviewWindowForm
from apps.reviews.models import ExamSetup, ReviewWindow


class ExamSetupUpdateView(ProfessorCourseMixin, UpdateView):
    model = ExamSetup
    form_class = ExamSetupForm
    template_name = "professor/exam_setup/form.html"

    def get_object(self, queryset=None):
        return get_or_create_exam_setup(self.course)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["course"] = self.course
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Exam setup saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("analytics_professor:exam_setup", kwargs={"course_pk": self.course.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "exam_setup"
        return context


class ReviewWindowListView(ProfessorCourseMixin, ListView):
    model = ReviewWindow
    template_name = "professor/windows/list.html"
    context_object_name = "windows"

    def get_queryset(self):
        return ReviewWindow.objects.filter(course=self.course).prefetch_related("topics")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "windows"
        now = timezone.now()
        context["upcoming_windows"] = [w for w in context["windows"] if w.opens_at > now]
        context["active_windows"] = [w for w in context["windows"] if w.is_open]
        context["past_windows"] = [
            w for w in context["windows"] if w.closes_at < now or not w.is_active
        ]
        return context


class ReviewWindowCreateView(ProfessorCourseMixin, CreateView):
    model = ReviewWindow
    form_class = ReviewWindowForm
    template_name = "professor/windows/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["course"] = self.course
        return kwargs

    def form_valid(self, form):
        form.instance.course = self.course
        form.instance.created_by = self.request.user
        messages.success(self.request, "Review window created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("analytics_professor:window_list", kwargs={"course_pk": self.course.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "windows"
        context["form_title"] = "Create Review Window"
        return context


class ReviewWindowUpdateView(ProfessorCourseMixin, UpdateView):
    model = ReviewWindow
    form_class = ReviewWindowForm
    template_name = "professor/windows/form.html"
    pk_url_kwarg = "window_pk"

    def get_queryset(self):
        return ReviewWindow.objects.filter(course=self.course)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["course"] = self.course
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Review window updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("analytics_professor:window_list", kwargs={"course_pk": self.course.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "windows"
        context["form_title"] = "Edit Review Window"
        return context


class ReviewWindowDeleteView(ProfessorCourseMixin, DeleteView):
    model = ReviewWindow
    template_name = "professor/windows/confirm_delete.html"
    pk_url_kwarg = "window_pk"

    def get_queryset(self):
        return ReviewWindow.objects.filter(course=self.course)

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, "Review window deactivated.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("analytics_professor:window_list", kwargs={"course_pk": self.course.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "windows"
        return context

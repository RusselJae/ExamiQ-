from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView, UpdateView

from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
)
from apps.core.mixins import ProfessorCourseMixin
from apps.analytics.services import get_step_feedback_stats
from apps.questions.forms import ExplanationStepFormSet
from apps.questions.models import Question


class FeedbackListView(ProfessorCourseMixin, ListView):
    model = Question
    template_name = "professor/feedback/list.html"
    context_object_name = "questions"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            Question.objects.filter(
                topic__subject__program=self.course.program,
                is_active=True,
                status=Question.Status.APPROVED,
            )
            .select_related("topic")
            .annotate(mistake_count=Count("mistake_records"))
            .filter(mistake_count__gt=0)
        )
        queryset = apply_date_range(queryset, self.request, "created")
        return apply_sort(
            queryset,
            self.request,
            newest_field="-mistake_count",
            oldest_field="mistake_count",
            default="newest",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "feedback"
        filter_names = ["date_from", "date_to", "sort"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            STANDARD_DATE_SORT_FILTER_SPECS,
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class FeedbackEditView(ProfessorCourseMixin, UpdateView):
    model = Question
    template_name = "professor/feedback/edit.html"
    pk_url_kwarg = "question_pk"
    fields = []

    def get_queryset(self):
        return Question.objects.filter(topic__subject__program=self.course.program)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["step_formset"] = ExplanationStepFormSet(self.request.POST, instance=self.object)
        else:
            context["step_formset"] = ExplanationStepFormSet(instance=self.object)
        context["active_tab"] = "feedback"
        context["mistake_count"] = self.object.mistake_records.count()
        context["step_stats"] = get_step_feedback_stats(self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_formset = ExplanationStepFormSet(request.POST, instance=self.object)
        if step_formset.is_valid():
            step_formset.save()
            messages.success(request, "Explanation feedback updated.")
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(step_formset=step_formset))

    def get_success_url(self):
        return reverse("analytics_professor:feedback_list", kwargs={"course_pk": self.course.pk})

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView, UpdateView

from apps.core.mixins import ProfessorCourseMixin
from apps.analytics.services import get_step_feedback_stats
from apps.questions.forms import ExplanationStepFormSet
from apps.questions.models import Question


class FeedbackListView(ProfessorCourseMixin, ListView):
    model = Question
    template_name = "professor/feedback/list.html"
    context_object_name = "questions"

    def get_queryset(self):
        return (
            Question.objects.filter(
                topic__subject__program=self.course.program,
                is_active=True,
                status=Question.Status.APPROVED,
            )
            .select_related("topic")
            .annotate(mistake_count=Count("mistake_records"))
            .filter(mistake_count__gt=0)
            .order_by("-mistake_count")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "feedback"
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

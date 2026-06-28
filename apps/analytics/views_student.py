from datetime import timedelta

from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.analytics.models import MistakeRecord
from apps.analytics.services import (
    generate_mistake_feedback,
    get_student_mistake_patterns,
    get_student_topic_answers,
    student_performance_summary,
    topic_progress_summary,
)
from apps.core.filtering import build_filter_fields, get_filter_param, has_active_filters
from apps.core.mixins import StudentRequiredMixin
from apps.questions.models import Question, Topic
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.recommendations import get_review_recommendations


class StudentDashboardView(StudentRequiredMixin, TemplateView):
    template_name = "analytics/student/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = student_performance_summary(self.request.user)
        context["recommendations"] = get_review_recommendations(self.request.user, limit=5)
        return context


class MistakeListView(StudentRequiredMixin, ListView):
    model = MistakeRecord
    template_name = "analytics/student/mistakes.html"
    context_object_name = "mistakes"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            MistakeRecord.objects.filter(student=self.request.user)
            .select_related("question", "topic", "answer")
            .order_by("-occurred_at")
        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(
                Q(topic__name__icontains=search) | Q(question__stem__icontains=search)
            )

        confidence_band = get_filter_param(self.request, "confidence")
        confidence_map = {"low": 1, "medium": 3, "high": 5}
        if confidence_band in confidence_map:
            queryset = queryset.filter(answer__confidence=confidence_map[confidence_band])

        recent = get_filter_param(self.request, "recent")
        days_map = {"7": 7, "30": 30, "90": 90}
        if recent in days_map:
            cutoff = timezone.now() - timedelta(days=days_map[recent])
            queryset = queryset.filter(occurred_at__gte=cutoff)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_names = ["q", "confidence", "recent"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Topic or question text",
                },
                {
                    "type": "select",
                    "name": "confidence",
                    "label": "Confidence",
                    "choices": [
                        ("low", "Low"),
                        ("medium", "Medium"),
                        ("high", "High"),
                    ],
                },
                {
                    "type": "select",
                    "name": "recent",
                    "label": "Date",
                    "all_label": "Any time",
                    "choices": [
                        ("7", "Last 7 days"),
                        ("30", "Last 30 days"),
                        ("90", "Last 90 days"),
                    ],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class MistakePatternView(StudentRequiredMixin, TemplateView):
    template_name = "analytics/student/mistake_patterns.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["patterns"] = get_student_mistake_patterns(self.request.user)
        return context


class TopicAnswerReviewView(StudentRequiredMixin, ListView):
    template_name = "analytics/student/topic_answer_review.html"
    context_object_name = "answers"
    paginate_by = 20

    def get_queryset(self):
        get_object_or_404(Topic, pk=self.kwargs["topic_id"])
        topic, answers = get_student_topic_answers(
            self.request.user,
            self.kwargs["topic_id"],
        )
        if not answers.exists():
            raise Http404
        self.topic = topic
        return answers

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["topic"] = self.topic
        return context


class SessionHistoryView(StudentRequiredMixin, ListView):
    model = ReviewSession
    template_name = "analytics/student/session_history.html"
    context_object_name = "sessions"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            ReviewSession.objects.filter(
                student=self.request.user,
                status__in=[ReviewSession.Status.COMPLETED, ReviewSession.Status.EXPIRED],
            )
            .select_related("topic", "course")
            .order_by("-started_at")
        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(topic__name__icontains=search)

        difficulty = get_filter_param(self.request, "difficulty")
        if difficulty in Question.Difficulty.values:
            queryset = queryset.filter(difficulty=difficulty)

        status = get_filter_param(self.request, "status")
        if status in {ReviewSession.Status.COMPLETED, ReviewSession.Status.EXPIRED}:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_names = ["q", "difficulty", "status"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Topic name",
                },
                {
                    "type": "select",
                    "name": "difficulty",
                    "label": "Difficulty",
                    "choices": Question.Difficulty.choices,
                },
                {
                    "type": "select",
                    "name": "status",
                    "label": "Status",
                    "choices": [
                        (ReviewSession.Status.COMPLETED, "Completed"),
                        (ReviewSession.Status.EXPIRED, "Expired"),
                    ],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class TopicProgressView(StudentRequiredMixin, TemplateView):
    template_name = "analytics/student/topic_progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["topics"] = topic_progress_summary(self.request.user)
        return context


class AnswerDetailView(StudentRequiredMixin, DetailView):
    model = Answer
    template_name = "analytics/student/answer_detail.html"
    context_object_name = "answer"
    pk_url_kwarg = "answer_pk"

    def get_queryset(self):
        return (
            Answer.objects.filter(session__student=self.request.user)
            .select_related(
                "question",
                "question__topic",
                "selected_choice",
                "mistake_record",
                "mistake_record__error_type",
            )
            .prefetch_related("question__choices", "question__explanation_steps")
        )


class GenerateAnswerFeedbackView(StudentRequiredMixin, View):
    """Generate AI feedback for a single wrong answer on demand."""

    def post(self, request, answer_pk):
        answer = get_object_or_404(
            Answer.objects.select_related(
                "question",
                "question__topic",
                "selected_choice",
                "mistake_record",
                "mistake_record__error_type",
                "session",
            ).prefetch_related("question__choices", "question__explanation_steps"),
            pk=answer_pk,
            session__student=request.user,
        )
        if answer.is_correct:
            return HttpResponse("Correct answers do not need feedback.", status=400)

        mistake_record = getattr(answer, "mistake_record", None)
        if not mistake_record:
            raise Http404

        generate_mistake_feedback(mistake_record)
        answer.refresh_from_db()
        answer.mistake_record.refresh_from_db()

        return render(
            request,
            "components/answer_review_card.html",
            {"answer": answer},
        )

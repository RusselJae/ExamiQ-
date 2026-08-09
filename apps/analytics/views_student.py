from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, RedirectView, TemplateView

from apps.analytics.concern_services import (
    concern_needs_student_attention,
    concern_thread_for,
    post_concern_message,
    serialize_concern_message,
    serialize_concern_thread,
    student_concern_queryset,
)
from apps.analytics.forms import MistakeConcernForm
from apps.analytics.models import MistakeRecord
from apps.analytics.services import (
    annotate_session_metrics,
    build_session_history_rows,
    generate_mistake_feedback,
    student_dashboard_trends,
    student_performance_summary,
    topic_progress_summary,
)
from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
)
from apps.core.mixins import StudentRequiredMixin
from apps.questions.models import Question, Topic
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.recommendations import get_review_recommendations


class StudentDashboardView(StudentRequiredMixin, TemplateView):
    template_name = "analytics/student/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dashboard_trends"] = student_dashboard_trends(self.request.user)
        context["summary"] = student_performance_summary(self.request.user)
        context["recommendations"] = get_review_recommendations(
            self.request.user, limit=5
        )
        return context


class MistakeListView(StudentRequiredMixin, ListView):
    model = MistakeRecord
    template_name = "analytics/student/mistakes.html"
    context_object_name = "mistakes"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            MistakeRecord.objects.filter(student=self.request.user)
            .select_related("question", "topic", "answer", "answer__session")
        )
        queryset = apply_date_range(queryset, self.request, "occurred_at")
        queryset = apply_sort(
            queryset,
            self.request,
            newest_field="-occurred_at",
            oldest_field="occurred_at",
        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(
                Q(topic__name__icontains=search) | Q(question__stem__icontains=search)
            )

        confidence_band = get_filter_param(self.request, "confidence")
        confidence_map = {"none": None, "low": 1, "average": 3, "high": 5}
        if confidence_band in confidence_map:
            value = confidence_map[confidence_band]
            if value is None:
                queryset = queryset.filter(answer__confidence__isnull=True)
            else:
                queryset = queryset.filter(answer__confidence=value)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_names = ["q", "confidence", "date_from", "date_to", "sort"]
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
                        ("none", "No Confidence"),
                        ("low", "Low Confidence"),
                        ("average", "Average Confidence"),
                        ("high", "High Confidence"),
                    ],
                },
                *STANDARD_DATE_SORT_FILTER_SPECS,
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        context["filter_bar_compact"] = True
        context["tutor_url_templates"] = {
            "history": reverse("reviews:tutor_history", kwargs={"pk": 0}).replace(
                "/0/", "/{pk}/"
            ),
            "chat": reverse("reviews:tutor_chat", kwargs={"pk": 0}).replace(
                "/0/", "/{pk}/"
            ),
            "feedback": reverse(
                "reviews:session_generate_feedback", kwargs={"pk": 0}
            ).replace("/0/", "/{pk}/"),
            "concern": reverse(
                "analytics_student:upload_mistake_concern", kwargs={"answer_pk": 0}
            ).replace("/0/", "/{pk}/"),
        }
        return context


class MistakePatternView(StudentRequiredMixin, RedirectView):
    """Weak Areas removed — redirect legacy URLs to Mistakes."""

    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("analytics_student:mistakes")


class TopicAnswerReviewView(StudentRequiredMixin, RedirectView):
    """Legacy weak-area topic drill-down — redirect to Mistakes."""

    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("analytics_student:mistakes")


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
        )
        queryset = apply_date_range(queryset, self.request, "started_at")
        queryset = apply_sort(
            queryset,
            self.request,
            newest_field="-started_at",
            oldest_field="started_at",
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

        return annotate_session_metrics(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_names = ["q", "difficulty", "status", "date_from", "date_to", "sort"]
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
                *STANDARD_DATE_SORT_FILTER_SPECS,
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        context["filter_bar_compact"] = True
        sessions = context.get("sessions") or context.get("object_list") or []
        context["session_history_rows"] = build_session_history_rows(sessions)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mistake = getattr(self.object, "mistake_record", None)
        if mistake:
            context["concern_form"] = MistakeConcernForm()
            thread = []
            for msg in concern_thread_for(mistake):
                entry = serialize_concern_message(msg)
                entry["created_at"] = msg.created_at
                thread.append(entry)
            if not thread:
                thread = [
                    {**entry, "created_at": None}
                    for entry in serialize_concern_thread(mistake)
                ]
            context["concern_messages"] = thread
        return context


class UploadMistakeConcernView(StudentRequiredMixin, View):
    """Append a student message (+ optional image) to a mistake concern thread."""

    def post(self, request, answer_pk):
        answer = get_object_or_404(
            Answer.objects.select_related("mistake_record", "session"),
            pk=answer_pk,
            session__student=request.user,
        )
        mistake_record = getattr(answer, "mistake_record", None)
        if answer.is_correct or not mistake_record:
            raise Http404

        wants_json = (
            "application/json" in (request.headers.get("Accept") or "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        form = MistakeConcernForm(request.POST, request.FILES)
        if form.is_valid():
            post_concern_message(
                mistake_record,
                request.user,
                body=form.cleaned_data["body"],
                image=form.cleaned_data.get("image"),
            )
            if wants_json:
                return JsonResponse(
                    {
                        "ok": True,
                        "messages": serialize_concern_thread(mistake_record),
                    }
                )
            messages.success(request, "Your message was sent.")
        else:
            error_text = form.errors.as_text() or "Could not save your note or image."
            if wants_json:
                return JsonResponse({"ok": False, "error": error_text}, status=400)
            messages.error(request, error_text)
        return redirect(
            reverse("analytics_student:answer_detail", kwargs={"answer_pk": answer.pk})
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


class StudentChatInboxView(StudentRequiredMixin, View):
    """Legacy chat page — open AI Tutor modal on the dashboard."""

    def get(self, request):
        url = reverse("analytics_student:dashboard")
        answer_id = request.GET.get("answer_id") or ""
        qs = "open_tutor=1"
        if answer_id:
            qs += f"&answer_id={answer_id}"
        return redirect(f"{url}?{qs}")


class StudentChatConcernsApiView(StudentRequiredMixin, View):
    """JSON list of the student's concern threads for the Chat modal."""

    def get(self, request):
        from apps.reviews.views_professor_feedback import _concern_item_payload

        records = list(student_concern_queryset(request.user)[:100])
        items = [_concern_item_payload(record) for record in records]
        # For students, peer label is still the student (self) in list — rename in UI via role
        active_id = request.GET.get("mistake_id")
        active_mistake_id = None
        if active_id and str(active_id).isdigit():
            active_mistake_id = int(active_id)
        elif items:
            active_mistake_id = items[0]["mistake_id"]
        return JsonResponse(
            {
                "items": items,
                "active_mistake_id": active_mistake_id,
            }
        )

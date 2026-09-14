from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, RedirectView, TemplateView

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
            .select_related(
                "question",
                "topic",
                "topic__subject",
                "answer",
                "answer__session",
            )
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
        return super().get_context_data(**kwargs)


class UploadMistakeConcernView(StudentRequiredMixin, View):
    """Deprecated — redirects chat to the unified student faculty thread."""

    def post(self, request, answer_pk):
        from apps.analytics.chat_services import (
            get_or_create_conversation,
            post_chat_message,
            serialize_conversation,
        )

        wants_json = (
            "application/json" in (request.headers.get("Accept") or "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        conversation = get_or_create_conversation(request.user)
        form = MistakeConcernForm(request.POST, request.FILES)
        if form.is_valid():
            post_chat_message(
                conversation,
                request.user,
                body=form.cleaned_data["body"],
                image=form.cleaned_data.get("image"),
            )
            if wants_json:
                return JsonResponse(
                    {
                        "ok": True,
                        "item": serialize_conversation(
                            conversation, viewer=request.user
                        ),
                    }
                )
            messages.success(request, "Your message was sent.")
        else:
            error_text = form.errors.as_text() or "Could not save your message."
            if wants_json:
                return JsonResponse({"ok": False, "error": error_text}, status=400)
            messages.error(request, error_text)
        return redirect(reverse("analytics_student:dashboard") + "?open_chat=1")


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
    """Legacy chat page — open Chat modal on the dashboard."""

    def get(self, request):
        url = reverse("analytics_student:dashboard")
        conversation_id = request.GET.get("conversation_id") or ""
        qs = "open_chat=1"
        if conversation_id:
            qs += f"&conversation_id={conversation_id}"
        return redirect(f"{url}?{qs}")


class StudentChatConversationsApiView(StudentRequiredMixin, View):
    """JSON list of the student's faculty chat thread for the Chat modal."""

    def get(self, request):
        from apps.analytics.chat_services import (
            get_or_create_conversation,
            mark_chat_notifications_read,
            serialize_conversation,
        )

        conversation = get_or_create_conversation(request.user)
        items = [serialize_conversation(conversation, viewer=request.user)]
        active_id = request.GET.get("conversation_id")
        active_conversation_id = conversation.pk
        if active_id and str(active_id).isdigit():
            active_conversation_id = int(active_id)
        mark_chat_notifications_read(
            request.user,
            conversation_id=active_conversation_id,
        )
        return JsonResponse(
            {
                "items": items,
                "active_conversation_id": active_conversation_id,
            }
        )


class StudentChatMessageView(StudentRequiredMixin, View):
    """Post a student message to the faculty chat thread."""

    def post(self, request):
        from apps.analytics.chat_services import (
            get_or_create_conversation,
            post_chat_message,
            serialize_conversation,
        )
        from apps.analytics.forms import MistakeConcernForm

        conversation = get_or_create_conversation(request.user)
        form = MistakeConcernForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "error": form.errors.as_text() or "Message cannot be empty."},
                status=400,
            )
        post_chat_message(
            conversation,
            request.user,
            body=form.cleaned_data["body"],
            image=form.cleaned_data.get("image"),
        )
        conversation.refresh_from_db()
        return JsonResponse(
            {
                "ok": True,
                "item": serialize_conversation(conversation, viewer=request.user),
            }
        )


# Backward-compatible alias
StudentChatConcernsApiView = StudentChatConversationsApiView


def _student_material_subjects(student):
    """Year-level and other-year exam subjects the student may browse."""
    from apps.reviews.exam_setup_services import (
        other_subjects_available_for_student,
        subjects_available_for_student,
    )

    year = list(subjects_available_for_student(student))
    other = list(other_subjects_available_for_student(student))
    seen: set[int] = set()
    subjects = []
    for subject in year + other:
        if subject.pk in seen:
            continue
        seen.add(subject.pk)
        subjects.append(subject)
    return subjects


def _student_can_access_subject(student, subject) -> bool:
    return any(s.pk == subject.pk for s in _student_material_subjects(student))


class StudentMaterialHubView(StudentRequiredMixin, TemplateView):
    """List course subjects with learning materials available to the student."""

    template_name = "analytics/student/materials_hub.html"

    def get_context_data(self, **kwargs):
        from apps.ai.material_services import ready_documents_for_subject
        from apps.questions.models import Subject, YearLevel

        context = super().get_context_data(**kwargs)
        cards = []
        for subject in _student_material_subjects(self.request.user):
            docs = ready_documents_for_subject(subject)
            cards.append(
                {
                    "subject": subject,
                    "document_count": len(docs),
                }
            )
        # Filters match the faculty course-subjects table toolbar
        context["subject_cards"] = cards
        context["year_levels"] = YearLevel.objects.order_by("order")
        context["semester_choices"] = Subject.Semester.choices
        return context


class StudentMaterialListView(StudentRequiredMixin, View):
    """Per-subject learning materials library (download-only)."""

    template_name = "analytics/student/materials_list.html"

    def get(self, request, subject_pk):
        from apps.ai.material_services import ready_documents_for_subject
        from apps.ai.models import LearningDocument
        from apps.questions.models import Subject

        subject = get_object_or_404(
            Subject.objects.select_related("year_level", "program"),
            pk=subject_pk,
        )
        if not _student_can_access_subject(request.user, subject):
            raise Http404
        documents = ready_documents_for_subject(subject)
        return render(
            request,
            self.template_name,
            {
                "subject": subject,
                "documents": documents,
                "library_count": len(documents),
                "material_types": LearningDocument.MaterialType.choices,
            },
        )


class StudentMaterialDownloadView(StudentRequiredMixin, View):
    """Authenticated download of a ready material for an accessible subject."""

    def get(self, request, subject_pk, pk):
        import mimetypes

        from apps.ai.material_services import (
            document_download_name,
            ready_documents_for_subject,
        )
        from apps.ai.models import LearningDocument
        from apps.questions.models import Subject
        from django.http import FileResponse

        subject = get_object_or_404(Subject, pk=subject_pk)
        if not _student_can_access_subject(request.user, subject):
            raise Http404
        allowed_ids = {doc.pk for doc in ready_documents_for_subject(subject)}
        if pk not in allowed_ids:
            raise Http404
        document = get_object_or_404(LearningDocument, pk=pk)
        if not document.file:
            raise Http404("File not available.")
        try:
            handle = document.file.open("rb")
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise Http404("File not available.") from exc
        filename = document_download_name(document)
        content_type, _ = mimetypes.guess_type(filename)
        return FileResponse(
            handle,
            as_attachment=True,
            filename=filename,
            content_type=content_type or "application/octet-stream",
        )

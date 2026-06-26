from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from apps.core.mixins import StudentRequiredMixin
from apps.questions.models import Question, Topic
from apps.questions.services import get_adaptive_questions_for_session
from apps.questions.views_curriculum import CurriculumSubjectsView, CurriculumTopicsView
from apps.reviews.recommendations import build_session_summary, get_review_recommendations
from apps.reviews.forms import AnswerForm, ReviewSetupForm
from apps.reviews.forms_professor import get_open_windows_for_student
from apps.reviews.models import Answer, ReviewSession, ReviewWindow
from apps.reviews.services import (
    SessionExpiredError,
    WindowStartError,
    complete_session,
    get_answered_question_ids,
    start_review_session,
    start_session_from_window,
    submit_answer,
    validate_session_active,
)


def _htmx_redirect_or_redirect(request, view_name, **kwargs):
    """Full-page redirect; HTMX requests use HX-Redirect instead of swapping HTML."""
    response = redirect(view_name, **kwargs)
    if request.headers.get("HX-Request"):
        htmx_response = HttpResponse(status=204)
        htmx_response["HX-Redirect"] = response.url
        return htmx_response
    return response


class ReviewSetupView(StudentRequiredMixin, View):
    """Select subject, topic, and difficulty to start a timed exam."""

    template_name = "reviews/setup.html"

    def get(self, request):
        open_windows = get_open_windows_for_student(request.user)
        form = ReviewSetupForm(student=request.user, open_windows=open_windows)
        return render(
            request,
            self.template_name,
            {"form": form, "open_windows": open_windows},
        )

    def post(self, request):
        open_windows = get_open_windows_for_student(request.user)
        form = ReviewSetupForm(request.POST, student=request.user, open_windows=open_windows)
        if form.is_valid():
            window = form.cleaned_data.get("review_window")
            course = form.get_course_for_session()
            mode = ReviewSession.Mode.TIMED_EXAM
            seconds_per_question = 30
            if window:
                mode = window.mode
                seconds_per_question = window.seconds_per_question
            session = start_review_session(
                student=request.user,
                topic=form.cleaned_data["topic"],
                difficulty=form.cleaned_data["difficulty"],
                duration_minutes=form.cleaned_data["duration_minutes"],
                course=course,
                review_window=window,
                mode=mode,
                seconds_per_question=seconds_per_question,
            )
            return redirect("reviews:session", pk=session.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "open_windows": open_windows},
        )


class ReviewSetupSubjectsView(StudentRequiredMixin, CurriculumSubjectsView):
    def get(self, request):
        program = request.user.home_program
        if not program:
            return JsonResponse({"subjects": []})
        request.GET = request.GET.copy()
        request.GET["program"] = str(program.pk)
        if request.user.year_level_id:
            request.GET["year_level"] = str(request.user.year_level_id)
        return super().get(request)


class ReviewSetupTopicsView(StudentRequiredMixin, CurriculumTopicsView):
    pass


class ReviewWindowStartView(StudentRequiredMixin, View):
    """Start a review session directly from an open review window."""

    def post(self, request, window_pk):
        open_window_ids = set(
            get_open_windows_for_student(request.user).values_list("pk", flat=True)
        )
        window = get_object_or_404(
            ReviewWindow.objects.select_related("course", "course__program").prefetch_related(
                "topics"
            ),
            pk=window_pk,
        )
        if window.pk not in open_window_ids:
            messages.error(request, "This review window is not available.")
            return redirect("reviews:setup")

        topic = None
        topic_id = request.POST.get("topic")
        if topic_id:
            topic = get_object_or_404(Topic, pk=topic_id)

        try:
            session = start_session_from_window(request.user, window, topic=topic)
        except WindowStartError as exc:
            messages.error(request, str(exc))
            return redirect("reviews:setup")

        return redirect("reviews:session", pk=session.pk)


class ReviewSessionView(StudentRequiredMixin, DetailView):
    """Active review session container."""

    model = ReviewSession
    template_name = "reviews/session.html"
    context_object_name = "session"

    def get_queryset(self):
        return ReviewSession.objects.filter(student=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["answered_count"] = self.object.answers.count()
        context["remaining_seconds"] = self.object.remaining_seconds
        context["is_timed_exam"] = self.object.mode == ReviewSession.Mode.TIMED_EXAM
        planned = self.object.planned_question_count
        answered = context["answered_count"]
        context["question_position"] = min(answered + 1, planned) if planned else answered + 1
        context["remaining_questions"] = max(0, (planned or 0) - answered)
        context["progress_percent"] = (
            int(answered / planned * 100) if planned else 0
        )
        context["question_dot_range"] = range(1, (planned or 0) + 1)
        return context


class QuestionPartialView(StudentRequiredMixin, View):
    """Load the next question or end the session."""

    def get_session(self, request, pk):
        return get_object_or_404(ReviewSession, pk=pk, student=request.user)

    def get(self, request, pk):
        session = self.get_session(request, pk)
        try:
            validate_session_active(session)
        except SessionExpiredError:
            complete_session(session)
            return _htmx_redirect_or_redirect(request, "reviews:summary", pk=session.pk)

        answered_ids = get_answered_question_ids(session)
        questions = get_adaptive_questions_for_session(
            session.student,
            session.topic,
            session.difficulty,
            count=1,
            exclude_ids=answered_ids,
        )
        question = questions.first()
        if not question:
            complete_session(session)
            return _htmx_redirect_or_redirect(request, "reviews:summary", pk=session.pk)

        timed_exam = session.mode == ReviewSession.Mode.TIMED_EXAM
        form = AnswerForm(question=question, timed_exam=timed_exam)
        return render(
            request,
            "reviews/partials/question.html",
            {
                "session": session,
                "question": question,
                "form": form,
                "is_timed_exam": timed_exam,
            },
        )


class SubmitAnswerView(StudentRequiredMixin, View):
    def post(self, request, pk, question_id):
        session = get_object_or_404(ReviewSession, pk=pk, student=request.user)
        question = get_object_or_404(Question, pk=question_id)
        timed_exam = session.mode == ReviewSession.Mode.TIMED_EXAM

        try:
            validate_session_active(session)
        except SessionExpiredError:
            complete_session(session)
            return _htmx_redirect_or_redirect(request, "reviews:summary", pk=session.pk)

        form = AnswerForm(request.POST, question=question, timed_exam=timed_exam)
        timed_out = request.POST.get("timed_out") == "true"

        if not timed_out and not form.is_valid():
            return render(
                request,
                "reviews/partials/question.html",
                {
                    "session": session,
                    "question": question,
                    "form": form,
                    "errors": True,
                    "is_timed_exam": timed_exam,
                },
            )

        time_spent = int(request.POST.get("time_spent_seconds", 0) or 0)
        confidence = None
        if not timed_out and form.is_valid():
            conf = form.cleaned_data.get("confidence")
            confidence = int(conf) if conf else None

        selected_choice = form.cleaned_data.get("selected_choice") if form.is_valid() else None
        numeric_response = form.cleaned_data.get("numeric_response", "") if form.is_valid() else ""

        answer = submit_answer(
            session=session,
            question=question,
            confidence=confidence,
            selected_choice=selected_choice,
            numeric_response=numeric_response,
            time_spent_seconds=time_spent,
            timed_out=timed_out,
        )

        if timed_exam:
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("reviews:session", kwargs={"pk": session.pk})
            return response

        steps = question.explanation_steps.all()
        return render(
            request,
            "reviews/partials/explanation.html",
            {"session": session, "answer": answer, "steps": steps},
        )


class SessionSummaryView(StudentRequiredMixin, DetailView):
    model = ReviewSession
    template_name = "reviews/summary.html"
    context_object_name = "session"

    def get_queryset(self):
        return (
            ReviewSession.objects.filter(student=self.request.user)
            .select_related("topic", "topic__subject")
            .prefetch_related(
                "answers__question__choices",
                "answers__question__explanation_steps",
                "answers__selected_choice",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["session_summary"] = build_session_summary(self.object)
        context["recommendations"] = get_review_recommendations(self.request.user, limit=5)
        context["answers"] = self.object.answers.select_related(
            "question", "selected_choice"
        ).prefetch_related("question__choices", "question__explanation_steps")
        return context


class FeedbackViewView(StudentRequiredMixin, View):
    def post(self, request, pk, answer_id):
        from apps.reviews.services import record_feedback_view

        session = get_object_or_404(ReviewSession, pk=pk, student=request.user)
        answer = get_object_or_404(Answer, pk=answer_id, session=session)
        record_feedback_view(answer)
        return HttpResponse(status=204)


class StepFeedbackViewView(StudentRequiredMixin, View):
    def post(self, request, pk, answer_id, step_id):
        from apps.questions.models import ExplanationStep
        from apps.reviews.services import record_step_feedback_view

        session = get_object_or_404(ReviewSession, pk=pk, student=request.user)
        answer = get_object_or_404(Answer, pk=answer_id, session=session)
        step = get_object_or_404(ExplanationStep, pk=step_id, question=answer.question)
        record_step_feedback_view(answer, step)
        return HttpResponse(status=204)


class SessionExpireView(StudentRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(ReviewSession, pk=pk, student=request.user)
        if session.status == ReviewSession.Status.ACTIVE:
            session.status = ReviewSession.Status.EXPIRED
            session.ended_at = timezone.now()
            session.save(update_fields=["status", "ended_at"])
        return redirect("reviews:summary", pk=session.pk)

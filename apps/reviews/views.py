from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from apps.core.mixins import StudentRequiredMixin
from apps.questions.curriculum import subject_queryset_for_student
from apps.questions.models import Question, Topic
from apps.questions.services import get_adaptive_questions_for_session
from apps.questions.views_curriculum import CurriculumSubjectsView, CurriculumTopicsView
from apps.reviews.exam_setup_services import student_setup_eligibility
from apps.reviews.recommendations import build_session_summary, get_review_recommendations
from apps.reviews.forms import AnswerForm, ReviewSetupForm
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.warmups import random_warmup
from apps.analytics.confidence import confidence_from_time_spent
from apps.reviews.services import (
    SessionExpiredError,
    complete_session,
    get_answered_question_ids,
    start_review_session,
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

    def _setup_context(self, form, **extra):
        import json

        eligibility = student_setup_eligibility(self.request.user)
        subjects = subject_queryset_for_student(self.request.user)
        no_exams = eligibility.get("eligible") and not subjects.exists()
        return {
            "form": form,
            "setup_eligibility": eligibility,
            "no_exams_available": no_exams,
            "warmup_json": json.dumps(random_warmup()),
            **extra,
        }

    def get(self, request):
        initial = {}
        preselected_topic_id = None

        topic_pk = request.GET.get("topic")
        if topic_pk:
            topic = get_object_or_404(Topic.objects.select_related("subject"), pk=topic_pk)
            if subject_queryset_for_student(request.user).filter(pk=topic.subject_id).exists():
                initial = {"subject": topic.subject, "topic": topic}
                preselected_topic_id = topic.pk

        form = ReviewSetupForm(student=request.user, initial=initial)
        return render(
            request,
            self.template_name,
            self._setup_context(form, preselected_topic_id=preselected_topic_id),
        )

    def post(self, request):
        form = ReviewSetupForm(request.POST, student=request.user)
        if form.is_valid():
            session = start_review_session(
                student=request.user,
                topic=form.cleaned_data["topic"],
                difficulty=form.cleaned_data["difficulty"],
                duration_minutes=form.cleaned_data["duration_minutes"],
                course=form.get_course_for_session(),
                mode=ReviewSession.Mode.TIMED_EXAM,
                pre_session_confidence=form.cleaned_data.get("pre_session_confidence") or "",
                session_goal=form.cleaned_data.get("session_goal") or "",
            )
            return redirect("reviews:session", pk=session.pk)
        return render(request, self.template_name, self._setup_context(form))


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
        if timed_exam:
            if timed_out:
                time_spent = session.seconds_per_question
            confidence = confidence_from_time_spent(time_spent)
        elif not timed_out and form.is_valid():
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
            response["HX-Redirect"] = reverse("reviews:question_partial", kwargs={"pk": session.pk})
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
                "answers__mistake_record",
                "answers__mistake_record__error_type",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_summary = build_session_summary(self.object)
        context["session_summary"] = session_summary
        context["calibration_tier_max"] = session_summary["calibration_tier_max"]
        context["recommendations"] = get_review_recommendations(self.request.user, limit=5)
        context["answers"] = (
            self.object.answers.select_related("question", "selected_choice", "mistake_record")
            .prefetch_related(
                "question__choices",
                "question__explanation_steps",
                "mistake_record__error_type",
            )
            .order_by("answered_at")
        )
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

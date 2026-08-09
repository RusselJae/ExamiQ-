from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from apps.core.mixins import StudentRequiredMixin
from apps.questions.models import Question, Topic
from apps.questions.services import count_available_questions, get_adaptive_questions_for_session
from apps.questions.views_curriculum import CurriculumSubjectsView, CurriculumTopicsView
from apps.reviews.exam_setup_services import (
    assignment_for_student_subject,
    exam_seconds_per_question,
    student_setup_eligibility,
)
from apps.reviews.recommendations import build_session_summary, get_review_recommendations
from apps.reviews.forms import AnswerForm, ReviewSetupForm
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.warmups import random_warmup
from apps.analytics.confidence import confidence_from_time_spent
from apps.reviews.services import (
    SessionExpiredError,
    complete_session,
    get_answered_question_ids,
    get_next_queued_question,
    session_has_more_questions,
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


def _question_partial_context(session, question, form, **extra):
    """Shared template context for the active question partial."""
    answered = session.answers.count()
    planned = session.planned_question_count or 0
    timed_exam = session.mode == ReviewSession.Mode.TIMED_EXAM
    context = {
        "session": session,
        "question": question,
        "form": form,
        "is_timed_exam": timed_exam,
        "answered_count": answered,
        "planned_question_count": planned,
        "question_position": min(answered + 1, planned) if planned else answered + 1,
        "progress_percent": int(answered / planned * 100) if planned else 0,
    }
    context.update(extra)
    return context


def _session_has_more_questions(session) -> bool:
    return session_has_more_questions(session)


def _is_last_timed_answer(session) -> bool:
    planned = session.planned_question_count or 0
    answered = session.answers.count()
    if planned and answered >= planned:
        return True
    return not _session_has_more_questions(session)


def _answer_reveal_context(session, question, answer, **extra):
    answered = session.answers.count()
    planned = session.planned_question_count or 0
    context = {
        "session": session,
        "question": question,
        "answer": answer,
        "is_timed_exam": True,
        "answered_count": answered,
        "planned_question_count": planned,
        "question_position": answered if planned else answered,
        "progress_percent": int(answered / planned * 100) if planned else 100,
        "is_last": _is_last_timed_answer(session),
    }
    context.update(extra)
    return context


def _exam_results_context(session):
    import math

    session_summary = build_session_summary(session)
    total = session_summary["total_questions"]
    incorrect = max(0, total - session_summary["correct_count"])
    circumference = 2 * math.pi * 42
    fraction = (session_summary["accuracy"] or 0) / 100
    suggestions = []
    if incorrect:
        suggestions.append("Review your mistakes before retaking")
    suggestions.append("Retake the exam once you feel confident")
    return {
        "session": session,
        "session_summary": session_summary,
        "incorrect_count": incorrect,
        "score_ring_dasharray": f"{circumference:.2f}",
        "score_ring_dashoffset": f"{circumference * (1 - fraction):.2f}",
        "suggestions": suggestions,
    }


def _exam_results_response(request, session):
    complete_session(session)
    return render(
        request,
        "reviews/partials/exam_results.html",
        _exam_results_context(session),
    )


def _next_question_response(request, session):
    """Return the next question partial or exam results when done."""
    try:
        validate_session_active(session)
    except SessionExpiredError:
        complete_session(session)
        if session.mode == ReviewSession.Mode.TIMED_EXAM:
            return _exam_results_response(request, session)
        return _htmx_redirect_or_redirect(request, "reviews:summary", pk=session.pk)

    question = None
    if session.question_queue:
        question = get_next_queued_question(session)
    else:
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
        if session.mode == ReviewSession.Mode.TIMED_EXAM:
            return _exam_results_response(request, session)
        complete_session(session)
        return _htmx_redirect_or_redirect(request, "reviews:summary", pk=session.pk)

    timed_exam = session.mode == ReviewSession.Mode.TIMED_EXAM
    form = AnswerForm(question=question, timed_exam=timed_exam)
    return render(
        request,
        "reviews/partials/question.html",
        _question_partial_context(session, question, form),
    )


class ReviewSetupView(StudentRequiredMixin, View):
    """Start a timed exam — multi-course + difficulty; wizard collects readiness."""

    template_name = "reviews/setup.html"

    def _setup_context(self, form, **extra):
        import json

        eligibility = student_setup_eligibility(self.request.user)
        no_exams = eligibility.get("reason") == "no_questions"
        return {
            "form": form,
            "setup_eligibility": eligibility,
            "no_exams_available": no_exams,
            "warmup_json": json.dumps(random_warmup()),
            **extra,
        }

    def get(self, request):
        form = ReviewSetupForm(student=request.user)
        return render(request, self.template_name, self._setup_context(form))

    def post(self, request):
        form = ReviewSetupForm(request.POST, student=request.user)
        if form.is_valid():
            target = form.get_auto_target()
            session = start_review_session(
                student=request.user,
                topic=target["topic"],
                difficulty=target["difficulty"],
                course=target.get("course"),
                mode=ReviewSession.Mode.TIMED_EXAM,
                duration_minutes=target["duration_minutes"],
                seconds_per_question=target["seconds_per_question"],
                question_queue=target["question_queue"],
                subjects=target["subjects"],
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


class ReviewSetupTimingView(StudentRequiredMixin, View):
    """GET ?subject=<pk> — exam timing configured by faculty for the student's section."""

    def get(self, request):
        from apps.questions.models import Subject
        from apps.reviews.exam_setup_services import assignment_for_student_subject, exam_seconds_per_question

        subject_id = request.GET.get("subject", "")
        if not subject_id.isdigit():
            return JsonResponse({})
        subject = Subject.objects.filter(pk=int(subject_id)).first()
        if not subject:
            return JsonResponse({})
        assignment = assignment_for_student_subject(request.user, subject)
        if not assignment or not assignment.course:
            return JsonResponse({})
        return JsonResponse({
            "seconds_per_question": exam_seconds_per_question(assignment.course),
        })


class ReviewSetupPreviewAPIView(StudentRequiredMixin, View):
    """GET ?topic=<pk> — question counts per difficulty and timing for exam preview."""

    def get(self, request):
        topic_id = request.GET.get("topic", "")
        if not topic_id.isdigit():
            return JsonResponse({})
        topic = Topic.objects.filter(pk=int(topic_id)).select_related("subject").first()
        if not topic:
            return JsonResponse({})
        assignment = assignment_for_student_subject(request.user, topic.subject)
        if not assignment or not assignment.course:
            return JsonResponse({})
        return JsonResponse({
            "easy": count_available_questions(topic, Question.Difficulty.EASY),
            "medium": count_available_questions(topic, Question.Difficulty.MEDIUM),
            "hard": count_available_questions(topic, Question.Difficulty.HARD),
            "seconds_per_question": exam_seconds_per_question(assignment.course),
        })


class ReviewSessionView(StudentRequiredMixin, DetailView):
    """Active review session container."""

    model = ReviewSession
    template_name = "reviews/session.html"
    context_object_name = "session"

    def get_queryset(self):
        return ReviewSession.objects.filter(student=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        answered = self.object.answers.count()
        planned = self.object.planned_question_count or 0
        context["answered_count"] = answered
        context["planned_question_count"] = planned
        context["remaining_seconds"] = self.object.remaining_seconds
        context["is_timed_exam"] = self.object.mode == ReviewSession.Mode.TIMED_EXAM
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
        if not request.headers.get("HX-Request"):
            return redirect("reviews:session", pk=pk)
        session = self.get_session(request, pk)
        return _next_question_response(request, session)


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
                _question_partial_context(session, question, form, errors=True),
            )

        time_spent = int(request.POST.get("time_spent_seconds", 0) or 0)
        confidence = None
        if timed_exam:
            if timed_out:
                time_spent = session.seconds_per_question
            confidence = confidence_from_time_spent(time_spent, session.seconds_per_question)
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
            return render(
                request,
                "reviews/partials/answer_reveal.html",
                _answer_reveal_context(session, question, answer),
            )

        steps = question.explanation_steps.all()
        return render(
            request,
            "reviews/partials/explanation.html",
            {"session": session, "answer": answer, "steps": steps},
        )


class ExamResultsPartialView(StudentRequiredMixin, View):
    """HTMX partial for timed exam results (focus layout)."""

    def get(self, request, pk):
        if not request.headers.get("HX-Request"):
            return redirect("reviews:session", pk=pk)
        session = get_object_or_404(ReviewSession, pk=pk, student=request.user)
        if session.status != ReviewSession.Status.COMPLETED:
            complete_session(session)
        return render(
            request,
            "reviews/partials/exam_results.html",
            _exam_results_context(session),
        )


class SessionSummaryView(StudentRequiredMixin, DetailView):
    model = ReviewSession
    template_name = "reviews/summary.html"
    context_object_name = "session"

    def get_queryset(self):
        return ReviewSession.objects.filter(student=self.request.user).select_related(
            "topic", "topic__subject"
        )

    def get_context_data(self, **kwargs):
        import math

        context = super().get_context_data(**kwargs)
        session_summary = build_session_summary(self.object)
        incorrect = max(
            0,
            session_summary["total_questions"] - session_summary["correct_count"],
        )
        circumference = 2 * math.pi * 42
        fraction = (session_summary["accuracy"] or 0) / 100
        context["session_summary"] = session_summary
        context["incorrect_count"] = incorrect
        context["score_ring_dasharray"] = f"{circumference:.2f}"
        context["score_ring_dashoffset"] = f"{circumference * (1 - fraction):.2f}"
        context["recommendations"] = get_review_recommendations(
            self.request.user, limit=5
        )
        context["feedback_url"] = reverse("reviews:session_generate_feedback", kwargs={"pk": self.object.pk})
        context["tutor_history_url"] = reverse("reviews:tutor_history", kwargs={"pk": self.object.pk})
        context["tutor_chat_url"] = reverse("reviews:tutor_chat", kwargs={"pk": self.object.pk})
        context["open_tutor"] = self.request.GET.get("open_tutor") == "1"
        return context


class SessionGenerateFeedbackView(StudentRequiredMixin, View):
    """Generate feedback for one answer, or all answers when answer_id is omitted."""

    def post(self, request, pk):
        from apps.analytics.confidence import confidence_tier_key
        from apps.analytics.services import generate_answer_feedback, generate_session_feedback

        session = get_object_or_404(
            ReviewSession,
            pk=pk,
            student=request.user,
            status=ReviewSession.Status.COMPLETED,
        )
        answer_id = request.GET.get("answer_id") or request.POST.get("answer_id")
        if answer_id is not None:
            try:
                answer_id = int(answer_id)
            except (TypeError, ValueError):
                return JsonResponse({"error": "Invalid answer_id."}, status=400)
            answer = get_object_or_404(
                Answer.objects.select_related(
                    "question", "selected_choice", "mistake_record"
                ).prefetch_related("question__choices"),
                pk=answer_id,
                session=session,
            )
            try:
                feedback = generate_answer_feedback(answer)
            except Exception:
                return JsonResponse(
                    {"error": "Feedback generation failed."},
                    status=500,
                )
            return JsonResponse(
                {
                    "items": [
                        {
                            "answer_id": answer.pk,
                            "stem": answer.question.stem,
                            "is_correct": answer.is_correct,
                            "timed_out": answer.timed_out,
                            "confidence_tier": confidence_tier_key(answer.confidence),
                            "feedback": feedback,
                            "needs_ai": False,
                        }
                    ]
                }
            )

        try:
            items = generate_session_feedback(session)
        except Exception:
            return JsonResponse(
                {"items": [], "error": "Feedback generation failed."},
                status=500,
            )
        for item in items:
            item["needs_ai"] = False
        return JsonResponse({"items": items})


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


class SessionTutorHistoryView(StudentRequiredMixin, View):
    def get(self, request, pk):
        session = get_object_or_404(
            ReviewSession,
            pk=pk,
            student=request.user,
            status=ReviewSession.Status.COMPLETED,
        )
        from apps.reviews.tutor_services import tutor_history_payload

        answer_id = request.GET.get("answer_id")
        if answer_id is not None:
            try:
                answer_id = int(answer_id)
            except (TypeError, ValueError):
                answer_id = None

        return JsonResponse(tutor_history_payload(session, answer_id=answer_id))


class SessionTutorChatView(StudentRequiredMixin, View):
    def post(self, request, pk):
        import json

        from apps.analytics.forms import MistakeConcernForm

        session = get_object_or_404(
            ReviewSession,
            pk=pk,
            student=request.user,
            status=ReviewSession.Status.COMPLETED,
        )
        content_type = (request.content_type or "").lower()
        image = None
        if "multipart/form-data" in content_type:
            message = (request.POST.get("message") or "").strip()
            answer_id = request.POST.get("answer_id")
            form = MistakeConcernForm(
                {"body": message},
                request.FILES,
            )
            if form.is_valid():
                message = form.cleaned_data.get("body") or ""
                image = form.cleaned_data.get("image")
            elif request.FILES.get("image"):
                return JsonResponse(
                    {"error": form.errors.as_text() or "Invalid image."},
                    status=400,
                )
        else:
            try:
                payload = json.loads(request.body.decode() or "{}")
            except json.JSONDecodeError:
                payload = {}
            message = (payload.get("message") or request.POST.get("message") or "").strip()
            answer_id = payload.get("answer_id") or request.POST.get("answer_id")

        if answer_id is not None:
            try:
                answer_id = int(answer_id)
            except (TypeError, ValueError):
                answer_id = None

        from apps.reviews.tutor_services import process_tutor_chat

        result = process_tutor_chat(
            session,
            message,
            answer_id=answer_id,
            image=image,
        )
        if result.get("error"):
            return JsonResponse(result, status=400)
        return JsonResponse(result)

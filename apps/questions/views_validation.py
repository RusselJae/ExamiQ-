"""Faculty random validation session views."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.core.mixins import ProfessorCourseMixin
from apps.questions.models import QuestionValidationItem, QuestionValidationSession
from apps.questions.validation_session_services import (
    clamp_validation_size,
    maybe_complete_session,
    record_validation_outcome,
    start_validation_session,
)
from apps.questions.views_professor import _subject_for_course, topics_for_course_section


class ValidationSessionStartView(ProfessorCourseMixin, View):
    template_name = "professor/validation/start.html"

    def get(self, request, course_pk):
        subject = _subject_for_course(self.course)
        topics = topics_for_course_section(self.course, request.user) if subject else []
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "active_tab": "validation",
                "subject": subject,
                "topics": topics,
                "default_size": clamp_validation_size(None),
            },
        )

    def post(self, request, course_pk):
        subject = _subject_for_course(self.course)
        if not subject:
            messages.error(request, "Link a subject to this course first.")
            return redirect("analytics_professor:validation_start", course_pk=course_pk)
        topic_id = request.POST.get("topic") or None
        topic = None
        if topic_id:
            topic = topics_for_course_section(self.course, request.user).filter(pk=topic_id).first()
        try:
            size = int(request.POST.get("size") or 0) or None
        except (TypeError, ValueError):
            size = None
        try:
            session = start_validation_session(
                faculty=request.user,
                subject=subject,
                topic=topic,
                size=size,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("analytics_professor:validation_start", course_pk=course_pk)
        return redirect(
            "analytics_professor:validation_detail",
            course_pk=course_pk,
            session_pk=session.pk,
        )


class ValidationSessionDetailView(ProfessorCourseMixin, View):
    template_name = "professor/validation/detail.html"

    def get_session(self, course_pk, session_pk):
        subject = _subject_for_course(self.course)
        return get_object_or_404(
            QuestionValidationSession.objects.prefetch_related(
                "items__question__choices",
                "items__question__explanation_steps",
            ),
            pk=session_pk,
            faculty=self.request.user,
            subject=subject,
        )

    def get(self, request, course_pk, session_pk):
        session = self.get_session(course_pk, session_pk)
        return render(
            request,
            self.template_name,
            {"course": self.course, "active_tab": "validation", "session": session, "items": session.items.all()},
        )

    def post(self, request, course_pk, session_pk):
        session = self.get_session(course_pk, session_pk)
        item_id = request.POST.get("item_id")
        item = get_object_or_404(QuestionValidationItem, pk=item_id, session=session)
        outcome = request.POST.get("outcome", QuestionValidationItem.Outcome.OK)
        notes = request.POST.get("notes", "")
        try:
            record_validation_outcome(
                item, outcome=outcome, notes=notes, faculty=request.user
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            maybe_complete_session(session)
            messages.success(request, "Saved review outcome.")
        return redirect(
            "analytics_professor:validation_detail",
            course_pk=course_pk,
            session_pk=session.pk,
        )

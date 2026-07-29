from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import ListView

from apps.analytics.concern_services import (
    _concern_activity_filter,
    concern_has_faculty_reply,
    concern_needs_faculty_reply,
    concern_queryset_with_messages,
    mark_concern_notifications_read,
    mark_faculty_viewed,
    post_concern_message,
    serialize_concern_thread,
)
from apps.analytics.models import MistakeRecord
from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
)
from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin
from apps.questions.models import Subject
from apps.reviews.tutor_services import _answer_correct_response, _answer_user_response


def _course_concern_queryset(course):
    """Mistake records with student concerns for a faculty course offering."""
    qs = MistakeRecord.objects.filter(
        question__topic__subject__program=course.program,
    )
    subject = Subject.objects.filter(code=course.code, program=course.program).first()
    if subject:
        qs = qs.filter(question__topic__subject=subject)
    return concern_queryset_with_messages(
        qs.filter(_concern_activity_filter())
        .select_related(
            "student",
            "question",
            "topic",
            "answer",
            "answer__selected_choice",
            "question__topic",
        )
        .prefetch_related("question__choices")
        .order_by("-occurred_at")
    )


def _concern_item_payload(record: MistakeRecord) -> dict:
    answer = record.answer
    messages = serialize_concern_thread(record)
    latest_student = next(
        (m for m in reversed(messages) if m["author_role"] == "student"),
        None,
    )
    return {
        "mistake_id": record.pk,
        "answer_id": answer.pk if answer else None,
        "student_name": record.student.get_full_name() or record.student.email,
        "student_email": record.student.email,
        "stem": record.question.stem,
        "topic": record.topic.name,
        "occurred_at": record.occurred_at.isoformat() if record.occurred_at else "",
        "user_answer": _answer_user_response(answer) if answer else "—",
        "correct_answer": _answer_correct_response(answer) if answer else "—",
        "ai_feedback": record.ai_feedback or "",
        "student_note": latest_student["body"] if latest_student else "",
        "student_image_url": latest_student["image_url"] if latest_student else "",
        "faculty_note": next(
            (m["body"] for m in reversed(messages) if m["author_role"] == "faculty"),
            "",
        ),
        "faculty_noted_at": next(
            (
                m["created_at"]
                for m in reversed(messages)
                if m["author_role"] == "faculty"
            ),
            "",
        ),
        "has_faculty_note": concern_has_faculty_reply(record),
        "needs_faculty_reply": concern_needs_faculty_reply(record),
        "messages": messages,
    }


def _section_concern_queryset(section):
    """Mistake records with student concerns from anyone in a ProgramSection."""
    return concern_queryset_with_messages(
        MistakeRecord.objects.filter(student__section=section)
        .filter(_concern_activity_filter())
        .select_related(
            "student",
            "question",
            "topic",
            "answer",
            "answer__selected_choice",
            "question__topic",
            "question__topic__subject",
        )
        .prefetch_related("question__choices")
        .order_by("-occurred_at")
    )


class FeedbackListView(ProfessorCourseMixin, ListView):
    """Inbox of student mistake concerns for this course."""

    model = MistakeRecord
    template_name = "professor/feedback/list.html"
    context_object_name = "concerns"
    paginate_by = 25

    def get_queryset(self):
        queryset = _course_concern_queryset(self.course)
        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(
                Q(student__email__icontains=search)
                | Q(student__first_name__icontains=search)
                | Q(student__last_name__icontains=search)
                | Q(question__stem__icontains=search)
                | Q(student_note__icontains=search)
                | Q(concern_messages__body__icontains=search)
            ).distinct()
        queryset = apply_date_range(queryset, self.request, "occurred_at")
        return apply_sort(
            queryset,
            self.request,
            newest_field="-occurred_at",
            oldest_field="occurred_at",
            default="newest",
        )

    def get_context_data(self, **kwargs):
        from apps.analytics.concern_services import pending_concern_count_for_course

        context = super().get_context_data(**kwargs)
        context["active_tab"] = "feedback"
        filter_names = ["q", "date_from", "date_to", "sort"]
        specs = [
            {
                "name": "q",
                "label": "Search",
                "type": "search",
                "placeholder": "Student, question, or note…",
            },
            *STANDARD_DATE_SORT_FILTER_SPECS,
        ]
        context["filter_form_fields"] = build_filter_fields(self.request, specs)
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        context["filter_bar_compact"] = True
        context["concern_items"] = [
            _concern_item_payload(record) for record in context["concerns"]
        ]
        context["pending_concern_count"] = pending_concern_count_for_course(self.course)
        return context


class FeedbackConcernsApiView(ProfessorCourseMixin, View):
    """JSON list of student concerns for the faculty feedback modal."""

    def get(self, request, course_pk):
        records = list(_course_concern_queryset(self.course)[:100])
        items = [_concern_item_payload(record) for record in records]
        active_id = request.GET.get("mistake_id")
        active_mistake_id = None
        if active_id and str(active_id).isdigit():
            active_mistake_id = int(active_id)
        elif items:
            active_mistake_id = items[0]["mistake_id"]

        if active_mistake_id:
            record = next((r for r in records if r.pk == active_mistake_id), None)
            if record:
                mark_faculty_viewed(record)
                mark_concern_notifications_read(request.user, active_mistake_id)

        return JsonResponse(
            {
                "items": items,
                "active_mistake_id": active_mistake_id,
            }
        )


class FeedbackFacultyNoteView(ProfessorCourseMixin, View):
    """Post a faculty reply in a student concern thread."""

    def post(self, request, course_pk, mistake_pk):
        record = get_object_or_404(
            _course_concern_queryset(self.course),
            pk=mistake_pk,
        )
        body = (request.POST.get("faculty_note") or request.POST.get("body") or "").strip()
        if not body:
            return JsonResponse({"ok": False, "error": "Reply cannot be empty."}, status=400)
        post_concern_message(record, request.user, body=body)
        record.refresh_from_db()
        return JsonResponse(
            {
                "ok": True,
                "item": _concern_item_payload(record),
            }
        )


class SectionFeedbackConcernsApiView(ProfessorRequiredMixin, View):
    """JSON list of section student concerns for the faculty feedback modal."""

    def dispatch(self, request, *args, **kwargs):
        from apps.users.models import ProgramSection

        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, section_pk):
        records = list(_section_concern_queryset(self.section)[:100])
        items = [_concern_item_payload(record) for record in records]
        active_id = request.GET.get("mistake_id")
        active_mistake_id = None
        if active_id and str(active_id).isdigit():
            active_mistake_id = int(active_id)
        elif items:
            active_mistake_id = items[0]["mistake_id"]

        if active_mistake_id:
            record = next((r for r in records if r.pk == active_mistake_id), None)
            if record:
                mark_faculty_viewed(record)
                mark_concern_notifications_read(request.user, active_mistake_id)

        return JsonResponse(
            {
                "items": items,
                "active_mistake_id": active_mistake_id,
            }
        )


class SectionFeedbackFacultyNoteView(ProfessorRequiredMixin, View):
    """Post a faculty reply on a section student concern."""

    def dispatch(self, request, *args, **kwargs):
        from apps.users.models import ProgramSection

        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, section_pk, mistake_pk):
        record = get_object_or_404(
            _section_concern_queryset(self.section),
            pk=mistake_pk,
        )
        body = (request.POST.get("faculty_note") or request.POST.get("body") or "").strip()
        if not body:
            return JsonResponse({"ok": False, "error": "Reply cannot be empty."}, status=400)
        post_concern_message(record, request.user, body=body)
        record.refresh_from_db()
        return JsonResponse(
            {
                "ok": True,
                "item": _concern_item_payload(record),
            }
        )

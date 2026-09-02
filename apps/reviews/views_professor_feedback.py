from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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
from apps.core.mixins import (
    FacultyLegacyRosterBlockedMixin,
    ProfessorCourseMixin,
    ProfessorRequiredMixin,
)
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
    from django.urls import reverse

    answer = record.answer
    messages = serialize_concern_thread(record)
    latest_student = next(
        (m for m in reversed(messages) if m["author_role"] == "student"),
        None,
    )
    latest_msg = messages[-1] if messages else None
    student = record.student
    name = student.get_full_name() or student.email
    if student.first_name and student.last_name:
        initials = (student.first_name[0] + student.last_name[0]).upper()
    else:
        initials = (name[:2] or "?").upper()
    subject = None
    if record.question_id and getattr(record.question, "topic_id", None):
        subject = getattr(record.question.topic, "subject", None)
    subject_code = subject.code if subject else ""
    from apps.analytics.concern_services import user_avatar_url

    # Faculty inbox preview: latest student message under the student name.
    preview = ""
    if latest_student:
        preview = (latest_student.get("body") or "").strip()
        if not preview and latest_student.get("image_url"):
            preview = "Sent an image"
    if not preview:
        preview = (record.question.stem or "")[:80]
    return {
        "mistake_id": record.pk,
        "answer_id": answer.pk if answer else None,
        "student_name": name,
        "student_email": student.email,
        "student_initials": initials,
        "student_avatar_url": user_avatar_url(student),
        "stem": record.question.stem,
        "topic": record.topic.name,
        "subject_code": subject_code,
        "preview": preview,
        "last_message_at": (
            (latest_msg.get("created_at") if latest_msg else "")
            or (record.occurred_at.isoformat() if record.occurred_at else "")
        ),
        "submitted_work_url": "",
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
        from apps.analytics.forms import MistakeConcernForm

        record = get_object_or_404(
            _course_concern_queryset(self.course),
            pk=mistake_pk,
        )
        form = MistakeConcernForm(
            {
                "body": (
                    request.POST.get("faculty_note")
                    or request.POST.get("body")
                    or ""
                ),
            },
            request.FILES,
        )
        if not form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "error": form.errors.as_text() or "Reply cannot be empty.",
                },
                status=400,
            )
        post_concern_message(
            record,
            request.user,
            body=form.cleaned_data["body"],
            image=form.cleaned_data.get("image"),
        )
        record.refresh_from_db()
        return JsonResponse(
            {
                "ok": True,
                "item": _concern_item_payload(record),
            }
        )


class SectionFeedbackConcernsApiView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, View):
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


class SectionFeedbackFacultyNoteView(FacultyLegacyRosterBlockedMixin, ProfessorRequiredMixin, View):
    """Post a faculty reply on a section student concern."""

    def dispatch(self, request, *args, **kwargs):
        from apps.users.models import ProgramSection

        self.section = get_object_or_404(
            ProgramSection.objects.select_related("program", "year_level"),
            pk=kwargs["section_pk"],
        )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, section_pk, mistake_pk):
        from apps.analytics.forms import MistakeConcernForm

        record = get_object_or_404(
            _section_concern_queryset(self.section),
            pk=mistake_pk,
        )
        form = MistakeConcernForm(
            {
                "body": (
                    request.POST.get("faculty_note")
                    or request.POST.get("body")
                    or ""
                ),
            },
            request.FILES,
        )
        if not form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "error": form.errors.as_text() or "Reply cannot be empty.",
                },
                status=400,
            )
        post_concern_message(
            record,
            request.user,
            body=form.cleaned_data["body"],
            image=form.cleaned_data.get("image"),
        )
        record.refresh_from_db()
        return JsonResponse(
            {
                "ok": True,
                "item": _concern_item_payload(record),
            }
        )


class GlobalChatInboxView(ProfessorRequiredMixin, View):
    """Legacy chat page — open global Chat modal on overview."""

    def get(self, request):
        url = reverse("analytics_professor:overview")
        student_id = request.GET.get("student_id") or ""
        conversation_id = request.GET.get("conversation_id") or ""
        qs = "open_chat=1"
        if student_id:
            qs += f"&student_id={student_id}"
        if conversation_id:
            qs += f"&conversation_id={conversation_id}"
        return redirect(f"{url}?{qs}")


class GlobalChatConversationsApiView(ProfessorRequiredMixin, View):
    """JSON list of student conversations for the global faculty Chat modal."""

    def get(self, request):
        from apps.analytics.chat_services import (
            mark_chat_notifications_read,
            professor_chat_queryset,
            serialize_conversation,
        )

        records = list(professor_chat_queryset(request.user)[:100])
        items = [serialize_conversation(record, viewer=request.user) for record in records]
        active_id = request.GET.get("conversation_id")
        student_id = request.GET.get("student_id")
        active_conversation_id = None
        if active_id and str(active_id).isdigit():
            active_conversation_id = int(active_id)
        elif student_id and str(student_id).isdigit():
            record = next(
                (r for r in records if r.student_id == int(student_id)),
                None,
            )
            if record:
                active_conversation_id = record.pk
        elif items:
            active_conversation_id = items[0]["conversation_id"]

        if active_conversation_id:
            record = next((r for r in records if r.pk == active_conversation_id), None)
            if record:
                mark_chat_notifications_read(
                    request.user,
                    conversation_id=active_conversation_id,
                    student_id=record.student_id,
                )

        return JsonResponse(
            {
                "items": items,
                "active_conversation_id": active_conversation_id,
            }
        )


class GlobalChatFacultyMessageView(ProfessorRequiredMixin, View):
    """Post a faculty reply from the global Chat inbox."""

    def post(self, request, conversation_pk):
        from apps.analytics.chat_services import (
            post_chat_message,
            professor_can_access_conversation,
            professor_chat_queryset,
            serialize_conversation,
        )
        from apps.analytics.forms import MistakeConcernForm

        conversation = get_object_or_404(
            professor_chat_queryset(request.user),
            pk=conversation_pk,
        )
        if not professor_can_access_conversation(request.user, conversation):
            return JsonResponse({"ok": False, "error": "Not allowed."}, status=403)

        form = MistakeConcernForm(
            {
                "body": (
                    request.POST.get("faculty_note")
                    or request.POST.get("body")
                    or ""
                ),
            },
            request.FILES,
        )
        if not form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "error": form.errors.as_text() or "Reply cannot be empty.",
                },
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


# Backward-compatible aliases
GlobalChatConcernsApiView = GlobalChatConversationsApiView
GlobalChatFacultyNoteView = GlobalChatFacultyMessageView

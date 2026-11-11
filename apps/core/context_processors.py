"""Template context processors for global navigation."""

from django.urls import reverse

from apps.users.assignment_services import get_professor_course_queryset
from apps.users.models import Course, Program, ProgramSection, User
from apps.users.notification_services import (
    recent_notifications,
    unread_notification_count,
)


def _managed_programs_for_nav(user: User):
    """Programs a campus admin or program coordinator may administer."""
    programs = Program.objects.all()
    if user.is_superuser or user.role == User.Role.CAMPUS_ADMIN:
        return programs
    if user.role == User.Role.PROGRAM_COORDINATOR and user.department_id:
        return programs.filter(managing_department=user.department)
    return programs.none()


def _coordinator_sections_for_nav(user: User) -> list[ProgramSection]:
    """Active sections for the coordinator/campus sidebar entity list."""
    return list(
        ProgramSection.objects.filter(
            program__in=_managed_programs_for_nav(user),
            is_active=True,
        )
        .select_related("program", "year_level", "academic_year")
        .order_by("program__name", "year_level__order", "label")[:40]
    )


def _professor_course_groups(user, courses: list) -> list[dict]:
    """Merge duplicate course rows by subject code for the faculty sidebar.

    One row per (program, code); offerings become section sub-rows with real
    student counts. Groups: PINNED (has drafts), THIS SEMESTER (current
    term), EARLIER TERMS (everything else, collapsed by default).
    """
    from collections import OrderedDict

    from django.db.models import Count

    from apps.reviews.models import ReviewSession

    if not courses:
        return []

    course_ids = [course.pk for course in courses]
    student_rows = (
        ReviewSession.objects.filter(course_id__in=course_ids)
        .values("course_id")
        .annotate(students=Count("student_id", distinct=True))
    )
    students_by_course = {row["course_id"]: row["students"] for row in student_rows}

    from apps.questions.models import Question

    draft_rows = (
        Question.objects.filter(
            topic__subject__program__in=[c.program_id for c in courses],
            status=Question.Status.DRAFT,
        )
        .values("topic__subject__code", "topic__subject__program_id")
        .annotate(drafts=Count("id"))
    )
    drafts_by_subject = {
        (row["topic__subject__program_id"], row["topic__subject__code"]): row["drafts"]
        for row in draft_rows
    }

    grouped: OrderedDict[tuple, dict] = OrderedDict()
    for course in courses:
        key = (course.program_id, course.code)
        group = grouped.get(key)
        if group is None:
            group = {
                "code": course.code,
                "name": course.name,
                "program_id": course.program_id,
                "term": course.term,
                "academic_year": course.academic_year,
                "representative_pk": course.pk,
                "draft_count": drafts_by_subject.get(
                    (course.program_id, course.code), 0
                ),
                "offerings": [],
            }
            grouped[key] = group
        section = (course.section or "").strip()
        group["offerings"].append(
            {
                "pk": course.pk,
                "section": section,
                "students": students_by_course.get(course.pk, 0),
            }
        )

    for group in grouped.values():
        group["offerings"].sort(key=lambda o: o["section"])
        real_sections = [
            o for o in group["offerings"] if o["section"] and o["section"] != "Catalog"
        ]
        group["sections"] = real_sections
        group["has_multiple_sections"] = len(real_sections) >= 2
        group["total_students"] = sum(o["students"] for o in group["offerings"])

    def _term_matches_current(group: dict) -> bool:
        """True when the group's term/year match the current academic term.

        Course terms are free text ("1st Sem") while AcademicTerm names are
        canonical ("1st Semester"), so compare on the semester number.
        """
        term = (group["term"] or "").strip().lower()
        normalized = term.replace("semester", "sem").replace("  ", " ").strip()
        current_name = (
            (current.name or "")
            .strip()
            .lower()
            .replace("semester", "sem")
            .replace("  ", " ")
            .strip()
        )
        return (
            bool(normalized)
            and normalized == current_name
            and (
                (group["academic_year"] or "").strip()
                == (current.academic_year.label or "").strip()
            )
        )

    current = None
    try:
        from apps.users.models import AcademicTerm

        current = AcademicTerm.get_current()
    except Exception:  # noqa: BLE001 - sidebar must never break on term lookup
        current = None

    pinned, current_term, earlier = [], [], []
    for group in grouped.values():
        if group["draft_count"] > 0:
            pinned.append(group)
        elif current is None or _term_matches_current(group):
            current_term.append(group)
        else:
            earlier.append(group)

    buckets = []
    if pinned:
        buckets.append({"key": "pinned", "label": "Pinned", "groups": pinned})
    if current_term:
        buckets.append(
            {"key": "current", "label": "This Semester", "groups": current_term}
        )
    if earlier:
        buckets.append(
            {
                "key": "earlier",
                "label": "Earlier Terms",
                "groups": earlier,
                "collapsed": True,
            }
        )
    return buckets


def navigation_context(request):
    """Provide role sidebar entity lists and active entity context."""
    from django.conf import settings

    from apps.core.breadcrumbs import build_nav_breadcrumbs

    context = {
        "max_pdf_upload_mb": settings.MATERIAL_UPLOAD_MAX_MB,
        "professor_courses": [],
        "student_subjects": [],
        "coordinator_sections": [],
        "professor_section_nav": [],
        "sidebar_course": None,
        "sidebar_section": None,
        "sidebar_section_label": "",
        "sidebar_subject": None,
        "sidebar_concept_count": 0,
        "summary_courses": [],
        "unread_notification_count": 0,
        "recent_notifications": [],
        "pending_concern_count": 0,
        "chat_inbox_url": "",
        "chat_concerns_url": "",
        "chat_conversations_url": "",
        "chat_note_url_base": "",
        "chat_message_url": "",
        "chat_concern_url_template": "",
        "faculty_chat_conversations_url": "",
        "faculty_chat_message_url": "",
        "faculty_chat_note_url_base": "",
        "show_chat_modal": False,
        "show_ai_tutor_modal": False,
        "tutor_url_templates": {},
        "tutor_default_session_id": None,
        "chat_self_avatar_url": "",
        "chat_self_initials": "",
        "chat_self_name": "",
        "nav_breadcrumbs": [],
    }
    user = request.user
    context["nav_breadcrumbs"] = build_nav_breadcrumbs(request)
    if not user.is_authenticated:
        return context

    context["unread_notification_count"] = unread_notification_count(user)
    from apps.users.notification_services import notification_icon_kind

    context["recent_notifications"] = recent_notifications(user, limit=8)
    for _notification in context["recent_notifications"]:
        _notification.icon_kind = notification_icon_kind(_notification)
    context["chat_self_name"] = user.get_full_name() or user.email
    context["chat_self_initials"] = user.initials
    if user.profile_photo:
        try:
            context["chat_self_avatar_url"] = user.profile_photo.url
        except ValueError:
            context["chat_self_avatar_url"] = ""

    match = getattr(request, "resolver_match", None)
    url_name = (match.url_name if match else "") or ""
    namespace = (match.namespace if match else "") or ""

    if user.role == User.Role.STUDENT:
        from apps.analytics.chat_services import pending_chat_count_for_student
        from apps.analytics.concept_review_services import concept_status_counts
        from apps.questions.models import Subject
        from apps.reviews.models import ReviewSession
        from apps.users.services import get_student_subjects

        # Action Plan badge: concepts the student still has to practise.
        context["sidebar_concept_count"] = concept_status_counts(user)["active"]
        context["pending_concern_count"] = pending_chat_count_for_student(user)
        context["chat_inbox_url"] = reverse("analytics_student:chat_inbox")
        context["chat_conversations_url"] = reverse(
            "analytics_student:chat_conversations_api"
        )
        context["chat_concerns_url"] = context["chat_conversations_url"]
        context["chat_message_url"] = reverse("analytics_student:chat_message")
        context["show_chat_modal"] = True
        context["show_ai_tutor_modal"] = True
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
        latest = (
            ReviewSession.objects.filter(
                student=user,
                status=ReviewSession.Status.COMPLETED,
            )
            .order_by("-ended_at", "-pk")
            .values_list("pk", flat=True)
            .first()
        )
        context["tutor_default_session_id"] = latest

        context["student_subjects"] = list(
            get_student_subjects(user)
            .select_related("year_level", "program")
            .order_by("year_level__order", "code")
        )

        subject_id = None
        if match and namespace == "analytics_student":
            subject_id = match.kwargs.get("subject_pk") or match.kwargs.get("pk")
            if url_name.startswith("materials") and subject_id:
                try:
                    context["sidebar_subject"] = Subject.objects.select_related(
                        "year_level", "program"
                    ).get(pk=subject_id)
                except Subject.DoesNotExist:
                    pass
        return context

    if user.role in {User.Role.PROGRAM_COORDINATOR, User.Role.CAMPUS_ADMIN}:
        context["coordinator_sections"] = _coordinator_sections_for_nav(user)
        if match and namespace == "campus" and "section" in url_name:
            section_id = match.kwargs.get("pk")
            if section_id:
                try:
                    context["sidebar_section"] = ProgramSection.objects.select_related(
                        "program", "year_level"
                    ).get(
                        pk=section_id,
                        program__in=_managed_programs_for_nav(user),
                    )
                except ProgramSection.DoesNotExist:
                    pass
        return context

    if user.role != User.Role.PROFESSOR:
        return context

    from apps.analytics.chat_services import pending_chat_count_for_professor

    context["pending_concern_count"] = pending_chat_count_for_professor(user)
    context["chat_inbox_url"] = reverse("analytics_professor:chat_inbox")
    context["chat_conversations_url"] = reverse(
        "analytics_professor:chat_conversations_api"
    )
    context["chat_concerns_url"] = context["chat_conversations_url"]
    context["chat_note_url_base"] = reverse(
        "analytics_professor:chat_faculty_message", kwargs={"conversation_pk": 0}
    )
    context["faculty_chat_conversations_url"] = reverse(
        "analytics_professor:faculty_chat_conversations_api"
    )
    context["faculty_chat_message_url"] = reverse(
        "analytics_professor:faculty_chat_message_start"
    )
    context["faculty_chat_note_url_base"] = reverse(
        "analytics_professor:faculty_chat_message", kwargs={"conversation_pk": 0}
    )
    context["show_chat_modal"] = True

    context["professor_courses"] = list(
        get_professor_course_queryset(user)
        .select_related("program")
        .order_by("code", "section", "-academic_year", "term")
    )

    # Sidebar shows only subjects this professor handles. Teaching-assignment
    # subjects win; otherwise fall back to the faculty profile selection.
    # An empty handled set means "not yet assigned", not "hide everything"
    # the legacy fallback queryset above may still carry.
    from apps.users.assignment_services import handled_subject_ids

    handled_ids = handled_subject_ids(user)
    if handled_ids:
        from apps.questions.models import Subject as _HandledSubject

        handled_codes = set(
            _HandledSubject.objects.filter(pk__in=handled_ids).values_list(
                "program_id", "code"
            )
        )
        context["professor_courses"] = [
            course
            for course in context["professor_courses"]
            if (course.program_id, course.code) in handled_codes
        ]

    # Merged course groups (one row per subject code) with draft + student
    # counts, section rows, and PINNED / THIS SEMESTER / EARLIER TERMS buckets.
    context["professor_course_groups"] = _professor_course_groups(
        user, context["professor_courses"]
    )
    context["summary_courses"] = [
        {
            "pk": course.pk,
            "code": course.code,
            "label": f"{course.code} — {(course.section or '').strip() or course.name}",
        }
        for course in context["professor_courses"]
    ]

    if not match or namespace != "analytics_professor":
        return context

    # Section URLs keep working if deep-linked; no sidebar section nav.
    if url_name.startswith("section_"):
        return context

    course_id = match.kwargs.get("course_pk") or match.kwargs.get("pk")
    # Subject analytics URLs still resolve a catalog course for sidebar tools
    if url_name in {"subject_detail", "subject_roster"}:
        from apps.questions.models import Subject
        from apps.users.assignment_services import get_or_create_catalog_course

        subject_id = match.kwargs.get("pk") or match.kwargs.get("subject_pk")
        if subject_id:
            try:
                subject = Subject.objects.select_related("program", "year_level").get(
                    pk=subject_id
                )
                context["sidebar_subject"] = subject
                context["sidebar_course"] = get_or_create_catalog_course(user, subject)
                context["sidebar_section_label"] = f"{subject.code} Catalog"
            except Subject.DoesNotExist:
                pass
        return context

    if course_id:
        try:
            course = Course.objects.select_related("program").get(
                pk=course_id,
                professor=user,
            )
            context["sidebar_course"] = course
            if (course.section or "").strip() == "Catalog":
                context["sidebar_section_label"] = f"{course.code} Catalog"
                from apps.questions.models import Subject

                context["sidebar_subject"] = Subject.objects.filter(
                    code=course.code, program=course.program
                ).first()
            else:
                context["sidebar_section_label"] = (
                    course.section or ""
                ).strip() or course.code
        except Course.DoesNotExist:
            pass

    # Currently selected section (?section=) shared by the viewing bar and
    # the sidebar section rows. Validated against sibling section labels.
    selected_section = ""
    sidebar_course = context.get("sidebar_course")
    if sidebar_course:
        raw_section = (request.GET.get("section") or "").strip()
        if raw_section:
            sibling_sections = {
                (c.section or "").strip()
                for c in context["professor_courses"]
                if c.program_id == sidebar_course.program_id
                and c.code == sidebar_course.code
            }
            sibling_sections.discard("")
            sibling_sections.discard("Catalog")
            if raw_section in sibling_sections:
                selected_section = raw_section
    context["selected_section"] = selected_section

    return context

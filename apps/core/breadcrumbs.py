"""Build hierarchical navbar breadcrumbs with spaced human labels."""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse

# Explicit labels for url names (underscores → multi-word Title Case).
# Keys are url_name only; namespace disambiguation happens in trail builders.
LABELS: dict[str, str] = {
    "home": "Home",
    "dashboard": "Dashboard",
    "overview": "Overview",
    "students": "Students",
    "professor_student_detail": "Student Detail",
    "student_detail": "Student Detail",
    "section_student_detail": "Student Detail",
    "session_review": "Session Review",
    "professor_answer_detail": "Answer Detail",
    "answer_detail": "Answer Detail",
    "chat_inbox": "Chat",
    "course_list": "Courses",
    "course_create": "Add Course",
    "course_detail": "Overview",
    "course_roster": "Roster",
    "course_heatmap": "Heatmap",
    "course_insights": "Insights",
    "exam_setup": "Exam Setup",
    "exam_setup_hub": "Exam Setup",
    "section_detail": "Section",
    "section_roster": "Roster",
    "section_exam_setup": "Exam Setup",
    "section_heatmap": "Heatmap",
    "section_feedback": "Feedback",
    "subject_detail": "Subject",
    "subject_roster": "Roster",
    "topic_list": "Topics",
    "topic_create": "Add Topic",
    "topic_edit": "Edit Topic",
    "question_list": "Saved Questions",
    "question_create": "Add Question",
    "question_create_single": "Add Question",
    "question_add": "Add Question",
    "question_edit": "Edit Question",
    "question_batch_edit": "Edit Question",
    "materials_hub": "Content",
    "material_list": "Content",
    "material_upload": "Upload Material",
    "material_detail": "Material",
    "feedback_list": "Feedback",
    "window_list": "Review Windows",
    "window_create": "Add Window",
    "window_edit": "Edit Window",
    "session_history": "Session History",
    "mistakes": "All Mistakes",
    "concept_review": "Concept Review",
    "mistake_patterns": "Mistake Patterns",
    "topic_progress": "Topic Progress",
    "topic_answer_review": "Topic Review",
    "materials_list": "Learning Materials",
    "materials_download": "Download",
    "setup": "Start Review",
    "setup_subjects": "Subjects",
    "setup_topics": "Topics",
    "setup_timing": "Timing",
    "session": "Review",
    "summary": "Summary",
    "profile": "Profile",
    "notifications": "Notifications",
    "user_list": "Accounts",
    "assignments": "Faculty Sections",
}


def humanize_url_name(url_name: str) -> str:
    """Turn ``student_detail`` into ``Student Detail`` (never ``Studentdetail``)."""
    if not url_name:
        return ""
    if url_name in LABELS:
        return LABELS[url_name]
    return url_name.replace("_", " ").replace("-", " ").title()


def _crumb(label: str, url: str | None = None) -> dict[str, Any]:
    return {"label": label, "url": url}


def _safe_reverse(viewname: str, **kwargs: Any) -> str | None:
    try:
        return reverse(viewname, kwargs=kwargs or None)
    except NoReverseMatch:
        try:
            return reverse(viewname)
        except NoReverseMatch:
            return None


def _course_from_kwargs(kwargs: dict[str, Any]):
    from apps.users.models import Course

    course_id = kwargs.get("course_pk") or kwargs.get("pk")
    if not course_id:
        return None
    return (
        Course.objects.filter(pk=course_id)
        .only("id", "code", "name", "section")
        .first()
    )


def _professor_course_trail(course) -> list[dict[str, Any]]:
    crumbs = [
        _crumb("Courses", _safe_reverse("analytics_professor:course_list")),
    ]
    if course:
        label = (course.code or "").strip().upper() or "Course"
        crumbs.append(
            _crumb(label, _safe_reverse("analytics_professor:course_detail", pk=course.pk))
        )
    return crumbs


def _build_professor_crumbs(
    url_name: str,
    kwargs: dict[str, Any],
    *,
    query: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    crumbs: list[dict[str, Any]] = []
    course_routes = {
        "course_detail",
        "course_roster",
        "course_heatmap",
        "course_insights",
        "exam_setup",
        "topic_list",
        "topic_create",
        "topic_edit",
        "question_list",
        "question_create",
        "question_create_single",
        "question_edit",
        "question_batch_edit",
        "materials_hub",
        "material_list",
        "material_upload",
        "material_detail",
        "feedback_list",
        "window_list",
        "window_create",
        "window_edit",
        "student_detail",
        "question_add",
    }
    if url_name in course_routes or kwargs.get("course_pk"):
        # For course_detail, pk is the course; for nested routes course_pk is set.
        course_kwargs = dict(kwargs)
        if url_name == "course_detail" and "course_pk" not in course_kwargs:
            course_kwargs["course_pk"] = course_kwargs.get("pk")
        course = _course_from_kwargs(course_kwargs)

        # Build combined label: "CODE - Page Label"
        if course:
            course_code = (course.code or "").strip().upper()
            page_label = humanize_url_name(url_name)
            if url_name == "course_detail":
                combined_label = f"{course_code} - Overview"
            elif url_name == "material_list":
                combined_label = f"{course_code} - Content"
            elif url_name == "question_list":
                combined_label = f"{course_code} - Saved Questions"
            else:
                combined_label = f"{course_code} - {page_label}"
            crumbs.extend(_professor_course_trail(course))
            # Replace the last crumb (course code) with combined label
            if crumbs and crumbs[-1]["label"] == course_code:
                crumbs[-1]["label"] = combined_label
                crumbs[-1]["url"] = None
        else:
            crumbs.append(_crumb(humanize_url_name(url_name), None))
        return crumbs

    if url_name == "professor_student_detail":
        crumbs.append(_crumb("Students", _safe_reverse("analytics_professor:students")))
        crumbs.append(_crumb("Student Detail", None))
        return crumbs

    if url_name.startswith("section_"):
        crumbs.append(_crumb(humanize_url_name(url_name), None))
        return crumbs

    crumbs.append(_crumb(humanize_url_name(url_name), None))
    return crumbs


def _build_student_crumbs(
    url_name: str,
    kwargs: dict[str, Any],
    *,
    query: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    crumbs: list[dict[str, Any]] = []
    query = query or {}

    if url_name == "mistakes":
        crumbs.append(_crumb("Action Plan", _safe_reverse("analytics_student:mistakes")))
        if query.get("tab") == "concepts":
            crumbs.append(_crumb("Concepts to Review", None))
        else:
            crumbs.append(_crumb("All Mistakes", None))
        return crumbs

    if url_name in {
        "concept_review",
        "concept_review_continue",
        "concept_review_try_it",
        "concept_review_practice",
        "concept_review_again",
    }:
        crumbs.append(_crumb("Action Plan", _safe_reverse("analytics_student:mistakes")))
        crumbs.append(
            _crumb(
                "Concepts to Review",
                _safe_reverse("analytics_student:mistakes") + "?tab=concepts",
            )
        )
        concept_label = "Concept Review"
        pk = kwargs.get("pk")
        if pk:
            from apps.analytics.models import ConceptReview

            review = (
                ConceptReview.objects.filter(pk=pk).only("concept_name").first()
            )
            if review and review.concept_name:
                concept_label = review.concept_name
        crumbs.append(_crumb(concept_label, None))
        return crumbs

    if url_name == "answer_detail":
        crumbs.append(_crumb("Action Plan", _safe_reverse("analytics_student:mistakes")))
        crumbs.append(_crumb("All Mistakes", _safe_reverse("analytics_student:mistakes")))
        crumbs.append(_crumb("Answer Detail", None))
        return crumbs

    if url_name in {"materials_list", "materials_download"}:
        crumbs.append(
            _crumb("Learning Materials", _safe_reverse("analytics_student:materials_hub"))
        )
        crumbs.append(_crumb(humanize_url_name(url_name), None))
        return crumbs

    crumbs.append(_crumb(humanize_url_name(url_name), None))
    return crumbs


def _build_reviews_crumbs(url_name: str) -> list[dict[str, Any]]:
    if url_name in {"setup", "setup_subjects", "setup_topics", "setup_timing"}:
        crumbs = [_crumb("Start Review", _safe_reverse("reviews:setup"))]
        if url_name != "setup":
            crumbs.append(_crumb(humanize_url_name(url_name), None))
        return crumbs
    if url_name in {"session", "summary", "exam_results"}:
        return [
            _crumb("Start Review", _safe_reverse("reviews:setup")),
            _crumb(humanize_url_name(url_name), None),
        ]
    return [_crumb(humanize_url_name(url_name), None)]


def build_nav_breadcrumbs(request) -> list[dict[str, Any]]:
    """Return ``[{label, url}]`` for the topbar; last item is the current page."""
    home_url = _safe_reverse("core:home")
    crumbs = [_crumb("Home", home_url)]

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return crumbs

    match = getattr(request, "resolver_match", None)
    if not match or not match.url_name:
        return crumbs

    url_name = match.url_name
    namespace = match.namespace or ""
    kwargs = dict(match.kwargs or {})
    query = {k: (v if isinstance(v, str) else v[0]) for k, v in request.GET.lists()}

    if url_name in {"home", "landing"} or namespace == "landing":
        return crumbs

    if namespace == "analytics_professor":
        crumbs.extend(_build_professor_crumbs(url_name, kwargs, query=query))
    elif namespace == "analytics_student":
        crumbs.extend(_build_student_crumbs(url_name, kwargs, query=query))
    elif namespace == "reviews":
        crumbs.extend(_build_reviews_crumbs(url_name))
    elif namespace == "users":
        crumbs.append(_crumb(humanize_url_name(url_name), None))
    elif namespace == "campus":
        crumbs.append(_crumb(humanize_url_name(url_name), None))
    elif namespace == "analytics_chairperson":
        crumbs.append(_crumb(humanize_url_name(url_name), None))
    else:
        crumbs.append(_crumb(humanize_url_name(url_name), None))

    # Cap: Home + up to 4 more segments.
    if len(crumbs) > 5:
        crumbs = [crumbs[0], *crumbs[-4:]]

    # Current page is never a link.
    if crumbs:
        crumbs[-1]["url"] = None

    return crumbs

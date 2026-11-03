"""Faculty content library views for learning materials."""

from __future__ import annotations

import json
import logging
import mimetypes
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.ai.ingest import (
    allowed_upload_suffixes,
    is_allowed_upload,
)
from apps.ai.material_services import (
    SourceMaterialError,
    archive_document,
    delete_document,
    document_download_name,
    documents_for_courses,
    documents_for_subject,
    ensure_download_file,
    ingest_course_material,
    replace_document_content,
    restore_document,
    update_document_metadata,
)
from apps.ai.office_editor import (
    STATUS_FORCE_SAVE as _STATUS_FORCE_SAVE,
)
from apps.ai.office_editor import (
    STATUS_READY_FOR_SAVE as _STATUS_READY_FOR_SAVE,
)
from apps.ai.office_editor import (
    OfficeEditorError,
    api_script_url,
    build_editor_config,
    document_from_token,
    download_edited_document,
    store_edited_document,
    verify_payload,
)
from apps.ai.office_editor import (
    absolute_url as office_absolute_url,
)
from apps.ai.office_editor import (
    file_token as office_file_token,
)
from apps.ai.office_editor import (
    is_editable as office_is_editable,
)

logger = logging.getLogger(__name__)

_SAVING_STATUSES = frozenset({_STATUS_READY_FOR_SAVE, _STATUS_FORCE_SAVE})
from apps.ai.models import LearningDocument
from apps.ai.source_extract import extract_pages_from_upload
from apps.ai.subject_relevance import assess_subject_relevance
from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin
from apps.questions.models import Subject, Topic
from apps.questions.views_professor import (
    _subject_for_course,
    subjects_for_course_section,
)
from apps.users.assignment_services import (
    get_or_create_catalog_course,
    get_professor_course_queryset,
    professor_can_access_subject,
)
from apps.users.models import User


def _bsed_subjects_queryset():
    """All BSEd Mathematics curriculum subjects for materials UI selects."""
    return (
        Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH)
        .select_related("program", "year_level")
        .order_by("year_level__order", "semester", "code")
    )


def _bsed_subject_options(professor):
    """BSED Math subjects with catalog courses for the materials hub."""
    options = []
    for subject in _bsed_subjects_queryset():
        course = get_or_create_catalog_course(professor, subject)
        options.append(
            {
                "subject": subject,
                "course": course,
                "label": f"{subject.code} — {subject.name}",
            }
        )
    return options


def _course_document_counts(course_ids):
    """One query for the file count of every catalog course (hub cards)."""
    if not course_ids:
        return {}
    counts = (
        LearningDocument.objects.filter(course_id__in=course_ids, is_archived=False)
        .values("course_id")
        .annotate(total=Count("id"))
    )
    return {row["course_id"]: row["total"] for row in counts}


def _subjects_for_material_detail(course, professor, document):
    """Subjects for the material detail course dropdown.

    Catalog hub offerings often yield an empty ``subjects_for_course_section``
    list; always expose BSEd Math subjects and ensure the document's subject
    remains selectable.
    """
    subjects = list(_bsed_subjects_queryset())
    section_subjects = subjects_for_course_section(course, professor).filter(
        program__slug=User.HomeDegreeProgram.BSED_MATH
    )
    by_id = {s.pk: s for s in subjects}
    for subject in section_subjects:
        by_id[subject.pk] = subject
    if (
        document.subject_id
        and document.subject_id not in by_id
        and document.subject is not None
    ):
        by_id[document.subject_id] = document.subject
    return sorted(
        by_id.values(),
        key=lambda s: (
            getattr(s.year_level, "order", 0) or 0,
            s.semester or 0,
            s.code or "",
        ),
    )


MATH_ONLY_UPLOAD_MESSAGE = "Content management accepts BSEd Mathematics subjects only."


def _is_math_subject(subject) -> bool:
    """Return True when ``subject`` belongs to the BSEd Mathematics curriculum."""
    program = getattr(subject, "program", None)
    return bool(program and program.slug == User.HomeDegreeProgram.BSED_MATH)


def _requested_subject(subject_id: str):
    """Fetch the explicitly posted subject, if any."""
    if subject_id and str(subject_id).isdigit():
        return (
            Subject.objects.select_related("program").filter(pk=int(subject_id)).first()
        )
    return None


def _resolve_upload_subject(course, professor, subject_id: str):
    """Pick a BSEd Mathematics subject from the request for this course.

    Hub uploads post an explicit ``subject_id``. Trust that when the subject is
    math and the professor may access it (catalog hub / assignments), even if
    ``subjects_for_course_section`` does not list it for the catalog shell.
    """
    subjects = subjects_for_course_section(course, professor).filter(
        program__slug=User.HomeDegreeProgram.BSED_MATH
    )
    requested = _requested_subject(subject_id)
    if requested is not None:
        if not _is_math_subject(requested):
            return None
        match = subjects.filter(pk=requested.pk).first()
        if match is not None:
            return match
        if professor_can_access_subject(professor, requested, course=course):
            return requested
        course_subject = _subject_for_course(course)
        if course_subject is not None and course_subject.pk == requested.pk:
            return requested
        return None
    course_subject = _subject_for_course(course)
    if _is_math_subject(course_subject):
        return course_subject
    return subjects.first()


def _file_response(document: LearningDocument) -> FileResponse:
    if not ensure_download_file(document):
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


def _ext_counts(documents) -> list[tuple[str, int]]:
    """File-extension counts for library filter chips (TXT, PDF, …)."""
    counts: dict[str, int] = {}
    for doc in documents:
        try:
            ext = (doc.file_type_label or "FILE").upper()
        except (AttributeError, TypeError, ValueError):
            ext = "FILE"
        counts[ext] = counts.get(ext, 0) + 1
    return sorted(counts.items())


def _hub_redirect_after_upload(subject_id: int | None, course_pk: int):
    if subject_id:
        return redirect(
            f"{reverse('analytics_professor:materials_hub')}?subject={subject_id}"
        )
    return redirect("analytics_professor:material_list", course_pk=course_pk)


def _extract_upload_pages(uploaded) -> tuple[list[dict], str]:
    """Extract pages once up front so the relevance gate can reuse them."""
    try:
        return extract_pages_from_upload(uploaded), ""
    except SourceMaterialError as exc:
        return [], str(exc)


def _unsupported_upload_message(name: str) -> str:
    """User-facing rejection for a file outside the supported upload set."""
    allowed = ", ".join(
        suffix.upper().lstrip(".") for suffix in allowed_upload_suffixes()
    )
    return f"{name or 'That file'} is not a supported format. Upload one of: {allowed}."


def _relevance_sample(pages: list[dict]) -> str:
    """Head + tail text, mirroring ``sample_material_for_relevance``.

    The opening carries the title/subject identity and the closing often holds
    the summary; a middle slice of a long chapter tells us much less.
    """
    if len(pages) <= 4:
        return " ".join(page["text"] for page in pages)
    head = " ".join(page["text"] for page in pages[:3])
    tail = pages[-1]["text"]
    return f"{head} {tail}"


def _relevance_rejection(subject, pages: list[dict]) -> str:
    """Return a message when the upload does not belong to ``subject``.

    Empty string means the upload passed (or could not be judged because no
    readable text was available — in that case ingest keeps the file for
    download with a warning rather than blocking a legitimate scan).
    """
    if not pages:
        return ""
    topics = list(Topic.objects.filter(subject=subject))
    verdict = assess_subject_relevance(_relevance_sample(pages), subject, topics)
    if verdict.get("related"):
        return ""
    reason = str(verdict.get("reason") or "").strip()
    if not reason:
        code = getattr(subject, "code", "") or ""
        name = getattr(subject, "name", "") or "this course subject"
        reason = (
            f"That file does not look related to {code} — {name}. "
            "Upload material that matches this course subject."
        )
    return reason


class MaterialHubView(ProfessorRequiredMixin, View):
    """Subject-gated upload + library (Add Questions style)."""

    template_name = "professor/materials/hub.html"

    def get(self, request):
        options = _bsed_subject_options(request.user)
        doc_counts = _course_document_counts([opt["course"].pk for opt in options])
        for opt in options:
            opt["doc_count"] = doc_counts.get(opt["course"].pk, 0)
        subject_id = request.GET.get("subject", "")
        course_id = request.GET.get("course", "")
        include_archived = request.GET.get("archived") == "1"

        selected_subject = None
        course = None
        if subject_id.isdigit():
            selected_subject = next(
                (
                    opt["subject"]
                    for opt in options
                    if opt["subject"].pk == int(subject_id)
                ),
                None,
            )
            if selected_subject:
                course = get_or_create_catalog_course(request.user, selected_subject)
        elif course_id.isdigit():
            course = next(
                (
                    opt["course"]
                    for opt in options
                    if opt["course"].pk == int(course_id)
                ),
                None,
            )
            if course:
                selected_subject = _subject_for_course(course) or next(
                    (
                        opt["subject"]
                        for opt in options
                        if opt["course"].pk == course.pk
                    ),
                    None,
                )

        hub_subject_selected = selected_subject is not None and course is not None
        documents = (
            documents_for_subject(selected_subject, include_archived=include_archived)
            if hub_subject_selected
            else LearningDocument.objects.none()
        )
        # Prefer subject-scoped list; fall back was already in documents_for_subject
        library_count = documents.count() if hub_subject_selected else 0

        return render(
            request,
            self.template_name,
            {
                "subject_options": options,
                "selected_subject": selected_subject,
                "selected_subject_pk": selected_subject.pk
                if selected_subject
                else None,
                "course": course,
                "hub_subject_selected": hub_subject_selected,
                "documents": documents,
                "include_archived": include_archived,
                "ext_counts": _ext_counts(documents),
                "library_count": library_count,
                "upload_url": (
                    reverse(
                        "analytics_professor:material_upload",
                        kwargs={"course_pk": course.pk},
                    )
                    if course
                    else ""
                ),
            },
        )


class MaterialListView(ProfessorCourseMixin, View):
    """Course-scoped learning materials (keeps course header + tabs)."""

    template_name = "professor/materials/list.html"

    def _section_scope(self):
        """Sibling offerings of this subject code the professor still teaches.

        Returns (offerings, labels): the offerings power the aggregated
        document list, the section labels back every "Viewing" tab.
        """
        offerings = list(
            get_professor_course_queryset(self.request.user).filter(
                code=self.course.code
            )
        )
        if not any(offering.pk == self.course.pk for offering in offerings):
            offerings.append(self.course)
        return offerings, []

    def get(self, request, course_pk):
        include_archived = request.GET.get("archived") == "1"
        subject = _subject_for_course(self.course)
        subjects = subjects_for_course_section(self.course, request.user)
        offerings, _labels = self._section_scope()
        scoped_offerings = offerings
        documents = documents_for_courses(
            [offering.pk for offering in scoped_offerings],
            include_archived=include_archived,
        )
        draft_count = 0
        if subject is not None:
            from apps.questions.models import Question

            draft_count = Question.objects.filter(
                topic__subject=subject,
                status=Question.Status.DRAFT,
            ).count()
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "subject": subject,
                "subjects": subjects,
                "subject_options": [
                    {"subject": s, "label": f"{s.code} — {s.name}"}
                    for s in _bsed_subjects_queryset()
                ],
                "active_tab": "content",
                "documents": documents,
                "include_archived": include_archived,
                "ext_counts": _ext_counts(documents),
                "library_count": documents.count(),
                "draft_count": draft_count,
            },
        )


class MaterialUploadView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):
        uploaded = request.FILES.get("source_file")
        subject_id = request.POST.get("subject_id", "")
        hub_return = request.POST.get("hub_return") == "1"
        if not uploaded:
            messages.error(request, "Choose a file to upload.")
            if hub_return and subject_id.isdigit():
                return _hub_redirect_after_upload(int(subject_id), course_pk)
            return redirect("analytics_professor:material_list", course_pk=course_pk)
        title = request.POST.get("title", "").strip()
        original_name = request.POST.get("original_name", "").strip()
        material_type = request.POST.get(
            "material_type", LearningDocument.MaterialType.MODULE
        )
        subject = _resolve_upload_subject(self.course, request.user, subject_id)

        def _reject(message):
            messages.error(request, message)
            if hub_return and subject:
                return _hub_redirect_after_upload(subject.pk, course_pk)
            return redirect("analytics_professor:material_list", course_pk=course_pk)

        if subject is None:
            requested = _requested_subject(subject_id)
            if requested is not None and not _is_math_subject(requested):
                return _reject(MATH_ONLY_UPLOAD_MESSAGE)
            return _reject(
                "Select a BSEd Mathematics course subject before uploading a "
                "learning material."
            )
        if not _is_math_subject(subject):
            return _reject(MATH_ONLY_UPLOAD_MESSAGE)

        # Reject unsupported formats before spending time on extraction.
        if not is_allowed_upload(uploaded.name):
            return _reject(_unsupported_upload_message(uploaded.name))

        # Extract once, then gate on subject relevance before creating anything.
        pages, extraction_error = _extract_upload_pages(uploaded)
        rejection = _relevance_rejection(subject, pages)
        if rejection:
            return _reject(rejection)

        try:
            doc = ingest_course_material(
                uploaded_file=uploaded,
                course_id=self.course.pk,
                user=request.user,
                title=title,
                material_type=material_type,
                subject=subject,
                original_name=original_name,
                pages=pages,
                extraction_error=extraction_error,
            )
        except SourceMaterialError as exc:
            messages.error(request, str(exc))
            if hub_return and subject:
                return _hub_redirect_after_upload(subject.pk, course_pk)
            return redirect("analytics_professor:material_list", course_pk=course_pk)
        description = request.POST.get("description", "").strip()
        if description:
            doc.description = description
            doc.save(update_fields=["description"])
        if doc.error_message:
            messages.warning(
                request,
                f"Uploaded “{doc.display_title}”. Students can download the "
                f"full file. {doc.error_message}",
            )
        else:
            messages.success(
                request,
                f"Uploaded “{doc.display_title}”. Students can download the full file.",
            )
        if hub_return and subject:
            return _hub_redirect_after_upload(subject.pk, course_pk)
        return redirect("analytics_professor:material_list", course_pk=course_pk)


class MaterialDetailView(ProfessorCourseMixin, View):
    template_name = "professor/materials/modal.html"

    def get_document(self, course_pk, pk):
        return get_object_or_404(
            LearningDocument.objects.select_related("subject"),
            pk=pk,
            course_id=course_pk,
        )

    def get(self, request, course_pk, pk):
        document = self.get_document(course_pk, pk)
        from_hub = request.GET.get("from") == "hub"
        if from_hub and document.subject_id:
            back_url = (
                f"{reverse('analytics_professor:materials_hub')}"
                f"?subject={document.subject_id}"
            )
        else:
            back_url = reverse(
                "analytics_professor:material_list",
                kwargs={"course_pk": course_pk},
            )
        size = None
        pages = None
        created_str = ""
        if document.file:
            try:
                size = document.file.size
            except (OSError, ValueError, TypeError):
                size = None
            pages = document.page_count
            if document.created:
                created_str = document.created.strftime("%b %d, %Y")
        download_url = (
            reverse(
                "analytics_professor:material_download",
                kwargs={"course_pk": course_pk, "pk": pk},
            )
            if document.file
            else ""
        )
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "active_tab": "content",
                "document": document,
                "from_hub": from_hub,
                "back_url": back_url,
                "download_url": download_url,
                "subjects": _subjects_for_material_detail(
                    self.course, request.user, document
                ),
                "attached_meta": (
                    f"{(size or 0) / 1024:.1f} KB · {pages or 0} page{'s' if (pages or 0) > 1 else ''} · Uploaded {created_str}"
                    if size or pages
                    else ""
                ),
                "subject_options": [
                    {"subject": s, "label": f"{s.code} — {s.name}"}
                    for s in _bsed_subjects_queryset()
                ],
            },
        )

    def post(self, request, course_pk, pk):
        document = self.get_document(course_pk, pk)
        action = request.POST.get("action", "save")
        subject_pk = document.subject_id
        hub_return = request.POST.get("hub_return") == "1"
        hub_subject_id = request.POST.get("subject_id", "")
        if hub_return and hub_subject_id.isdigit():
            subject_pk = int(hub_subject_id)

        def _after_mutate():
            if hub_return and subject_pk:
                return _hub_redirect_after_upload(subject_pk, course_pk)
            return redirect("analytics_professor:material_list", course_pk=course_pk)

        if action == "archive":
            archive_document(document)
            messages.success(request, "Material archived.")
            return _after_mutate()
        if action == "restore":
            restore_document(document)
            messages.success(request, "Material restored.")
            return redirect(
                "analytics_professor:material_detail", course_pk=course_pk, pk=pk
            )
        if action == "delete":
            title = document.display_title
            delete_document(document)
            messages.success(request, f"“{title}” was deleted permanently.")
            return _after_mutate()
        if action == "save_content":
            try:
                result = replace_document_content(
                    document, html=request.POST.get("content_html")
                )
            except SourceMaterialError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Content saved — {result['chunk_count']} chunk(s) rebuilt for "
                    "AI generate.",
                )
                if result["file_kept_original"]:
                    messages.info(
                        request,
                        "The download is a PDF, so students still receive the "
                        "original upload. The content you edited is what AI "
                        "generate uses.",
                    )
            return redirect(
                "analytics_professor:material_detail", course_pk=course_pk, pk=pk
            )
        if action == "replace_file":
            return self._replace_file(request, course_pk, pk, document)
        subject = _resolve_upload_subject(
            self.course, request.user, request.POST.get("subject_id", "")
        )
        if subject is None:
            messages.error(request, MATH_ONLY_UPLOAD_MESSAGE)
            return redirect(
                "analytics_professor:material_detail", course_pk=course_pk, pk=pk
            )
        if not _is_math_subject(subject):
            messages.error(request, MATH_ONLY_UPLOAD_MESSAGE)
            return redirect(
                "analytics_professor:material_detail", course_pk=course_pk, pk=pk
            )
        update_document_metadata(
            document,
            title=request.POST.get("title", document.title),
            material_type=request.POST.get("material_type", document.material_type),
            original_name=request.POST.get("original_name", document.original_name),
            subject=subject,
        )
        description = request.POST.get("description")
        if description is not None:
            document.description = description.strip()
            document.save(update_fields=["description"])
        # The editor lives inside this form: when the content changed, the
        # submitted HTML is saved too and the AI chunks are rebuilt.
        content_html = request.POST.get("content_html", "")
        if content_html.strip():
            try:
                result = replace_document_content(document, html=content_html)
            except SourceMaterialError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Material updated — {result['chunk_count']} chunk(s) rebuilt "
                    "for AI generate.",
                )
        else:
            messages.success(request, "Material updated.")
        return self._modal_redirect(request, course_pk, pk, subject_pk)

    def _modal_redirect(self, request, course_pk, pk, subject_pk):
        """Send Edit-modal posts back to where they were raised from."""
        hub_return = request.POST.get("hub_return") == "1"
        if hub_return and subject_pk:
            return _hub_redirect_after_upload(subject_pk, course_pk)
        return_target = request.POST.get("return_to", "")
        if return_target == "hub":
            return redirect("analytics_professor:materials_hub")
        if return_target == "list":
            return redirect("analytics_professor:material_list", course_pk=course_pk)
        return redirect(
            "analytics_professor:material_detail", course_pk=course_pk, pk=pk
        )

    def _replace_file(self, request, course_pk, pk, document):
        """Swap the file behind an existing document (Edit modal action).

        The old upload is archived and the replacement runs through the normal
        ingest pipeline, so chunks/status stay consistent. If ingest fails the
        original document is restored untouched.
        """
        subject_pk = document.subject_id
        uploaded = request.FILES.get("replace_file") or request.FILES.get("source_file")
        if uploaded is None:
            messages.error(request, "Choose a file to replace the current upload.")
            return self._modal_redirect(request, course_pk, pk, subject_pk)
        if not is_allowed_upload(uploaded.name):
            messages.error(request, _unsupported_upload_message(uploaded.name))
            return self._modal_redirect(request, course_pk, pk, subject_pk)

        pages, extraction_error = _extract_upload_pages(uploaded)
        title = document.display_title
        original_description = document.description

        archive_document(document)
        try:
            new_doc = ingest_course_material(
                uploaded_file=uploaded,
                course_id=self.course.pk,
                user=request.user,
                title=title,
                material_type=document.material_type,
                subject=document.subject,
                original_name="",
                pages=pages,
                extraction_error=extraction_error,
            )
        except SourceMaterialError as exc:
            restore_document(document)
            messages.error(request, str(exc))
            return self._modal_redirect(request, course_pk, pk, subject_pk)
        if original_description:
            new_doc.description = original_description
            new_doc.save(update_fields=["description"])
        if new_doc.error_message:
            messages.warning(
                request,
                f"File replaced with “{new_doc.display_title}”. Students can "
                f"download the full file. {new_doc.error_message}",
            )
        else:
            messages.success(request, "File replaced.")
        return self._modal_redirect(
            request, course_pk, pk, new_doc.subject_id or subject_pk
        )


class MaterialDownloadView(ProfessorCourseMixin, View):
    """Authenticated download for a course learning material."""

    def get(self, request, course_pk, pk):
        document = get_object_or_404(
            LearningDocument.objects.filter(course_id=course_pk),
            pk=pk,
        )
        return _file_response(document)


def _office_enabled_response():
    return JsonResponse(
        {
            "enabled": False,
            "api_url": "",
            "document": None,
            "config": None,
        }
    )


class MaterialOfficeConfigView(ProfessorCourseMixin, View):
    """Editor config for the embedded ONLYOFFICE viewer."""

    def post(self, request, course_pk, pk):
        document = get_object_or_404(
            LearningDocument.objects.filter(course_id=course_pk), pk=pk
        )
        if not office_is_editable(document):
            return _office_enabled_response()

        file_url = office_absolute_url(
            request,
            reverse(
                "analytics_professor:material_office_file",
                kwargs={"course_pk": course_pk, "pk": pk},
            ),
        )
        file_url = f"{file_url}?token={quote(office_file_token(document))}"
        callback_url = office_absolute_url(
            request,
            reverse(
                "analytics_professor:material_office_callback",
                kwargs={"course_pk": course_pk, "pk": pk},
            ),
        )
        try:
            config = build_editor_config(
                document,
                user=request.user,
                file_url=file_url,
                callback_url=callback_url,
            )
        except OfficeEditorError as exc:
            return JsonResponse({"enabled": False, "error": str(exc)}, status=503)
        return JsonResponse(
            {
                "enabled": True,
                "api_url": api_script_url(),
                "document_key": config["document"]["key"],
                "config": config,
            }
        )


class MaterialOfficeFileView(View):
    """Serves the stored file to the Document Server using a signed token.

    Deliberately unauthenticated: the Document Server fetches server-to-server
    and carries no session cookie. Access is granted by the signed, short-lived,
    path-bound token instead.
    """

    def get(self, request, course_pk, pk):
        token = request.GET.get("token", "")
        document = document_from_token(token)
        if document is None or document.pk != int(pk):
            raise Http404("Invalid or expired document token.")
        if document.course_id != int(course_pk):
            raise Http404("Invalid or expired document token.")
        return _file_response(document)


@method_decorator(csrf_exempt, name="dispatch")
class MaterialOfficeCallbackView(View):
    """Receives ONLYOFFICE save notifications and stores the edited file.

    CSRF is exempt because the Document Server is not a browser and cannot
    carry a token. Authenticity comes from the signed JWT instead, which
    ``verify_payload`` checks before any bytes are written.
    """

    def post(self, request, course_pk, pk):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": 1}, status=400)

        document = get_object_or_404(
            LearningDocument.objects.filter(course_id=course_pk), pk=pk
        )
        try:
            payload = verify_payload(body)
        except OfficeEditorError as exc:
            logger.warning("Rejected ONLYOFFICE callback: %s", exc)
            return JsonResponse({"error": 1}, status=403)

        status = payload.get("status")
        if status not in _SAVING_STATUSES:
            # 1 editing, 3/4 closed, 7 error - nothing to store.
            return JsonResponse({"error": 0})

        url = (payload.get("url") or "").strip()
        try:
            data = download_edited_document(document, url)
            store_edited_document(document, data)
        except OfficeEditorError as exc:
            logger.warning("ONLYOFFICE save failed for document %s: %s", pk, exc)
            return JsonResponse({"error": 1}, status=400)
        return JsonResponse({"error": 0})

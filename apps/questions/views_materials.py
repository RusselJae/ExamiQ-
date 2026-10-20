"""Faculty content library views for learning materials."""

from __future__ import annotations

import json
import logging
import mimetypes
from urllib.parse import quote

from django.contrib import messages
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
    document_download_name,
    document_editor_html,
    document_plain_text,
    document_text_is_rewritable,
    documents_for_course,
    documents_for_subject,
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
    professor_can_access_subject,
)
from apps.users.models import User


def _bsed_subject_options(professor):
    """BSED Math subjects with catalog courses for the materials hub."""
    subjects = (
        Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH)
        .select_related("program", "year_level")
        .order_by("year_level__order", "semester", "code")
    )
    options = []
    for subject in subjects:
        course = get_or_create_catalog_course(professor, subject)
        options.append(
            {
                "subject": subject,
                "course": course,
                "label": f"{subject.code} — {subject.name}",
            }
        )
    return options


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

    def get(self, request, course_pk):
        include_archived = request.GET.get("archived") == "1"
        subject = _subject_for_course(self.course)
        subjects = subjects_for_course_section(self.course, request.user)
        documents = documents_for_course(
            self.course.pk, include_archived=include_archived
        )
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "subject": subject,
                "subjects": subjects,
                "active_tab": "materials",
                "documents": documents,
                "include_archived": include_archived,
                "ext_counts": _ext_counts(documents),
                "library_count": documents.count(),
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
    template_name = "professor/materials/detail.html"

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
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "active_tab": "materials",
                "document": document,
                "subjects": subjects_for_course_section(self.course, request.user),
                "chunks_preview": document.chunks.order_by("order")[:5],
                "document_text": document_plain_text(document),
                "document_html": document_editor_html(document),
                "text_is_rewritable": document_text_is_rewritable(document),
                "is_pdf": document.is_pdf,
                "office_enabled": office_is_editable(document),
                "office_config_url": (
                    reverse(
                        "analytics_professor:material_office_config",
                        kwargs={"course_pk": course_pk, "pk": pk},
                    )
                    if office_is_editable(document)
                    else ""
                ),
                "back_url": back_url,
                "from_hub": from_hub,
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
        messages.success(request, "Material updated.")
        return redirect(
            "analytics_professor:material_detail", course_pk=course_pk, pk=pk
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

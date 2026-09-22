"""Faculty content library views for learning materials."""

from __future__ import annotations

import mimetypes

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.ai.material_services import (
    SourceMaterialError,
    archive_document,
    document_download_name,
    documents_for_course,
    documents_for_subject,
    ingest_course_material,
    restore_document,
    update_document_metadata,
)
from apps.ai.models import LearningDocument
from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin
from apps.questions.models import Subject
from apps.questions.views_professor import (
    _subject_for_course,
    subjects_for_course_section,
)
from apps.users.assignment_services import get_or_create_catalog_course
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


def _resolve_upload_subject(course, professor, subject_id: str):
    """Pick a subject from the request, constrained to the course section."""
    subjects = subjects_for_course_section(course, professor)
    if subject_id and str(subject_id).isdigit():
        match = subjects.filter(pk=int(subject_id)).first()
        if match is not None:
            return match
    return _subject_for_course(course) or subjects.first()


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


def _hub_redirect_after_upload(subject_id: int | None, course_pk: int):
    if subject_id:
        return redirect(
            f"{reverse('analytics_professor:materials_hub')}?subject={subject_id}"
        )
    return redirect("analytics_professor:material_list", course_pk=course_pk)


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
                (opt["course"] for opt in options if opt["course"].pk == int(course_id)),
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
                "selected_subject_pk": selected_subject.pk if selected_subject else None,
                "course": course,
                "hub_subject_selected": hub_subject_selected,
                "documents": documents,
                "include_archived": include_archived,
                "material_types": LearningDocument.MaterialType.choices,
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
    """Redirect course materials into the subject-gated hub."""

    def get(self, request, course_pk):
        subject = _subject_for_course(self.course)
        if subject:
            url = reverse("analytics_professor:materials_hub")
            qs = f"?subject={subject.pk}"
            if request.GET.get("archived") == "1":
                qs += "&archived=1"
            return redirect(url + qs)
        return redirect("analytics_professor:materials_hub")


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
        if subject is None and subject_id.isdigit():
            subject = Subject.objects.filter(pk=int(subject_id)).first()
        try:
            doc = ingest_course_material(
                uploaded_file=uploaded,
                course_id=self.course.pk,
                user=request.user,
                title=title,
                material_type=material_type,
                subject=subject,
                original_name=original_name,
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
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "active_tab": "materials",
                "document": document,
                "subjects": subjects_for_course_section(self.course, request.user),
                "material_types": LearningDocument.MaterialType.choices,
                "chunks_preview": document.chunks.order_by("order")[:5],
                "back_url": (
                    f"{reverse('analytics_professor:materials_hub')}?subject={document.subject_id}"
                    if document.subject_id
                    else reverse("analytics_professor:materials_hub")
                ),
            },
        )

    def post(self, request, course_pk, pk):
        document = self.get_document(course_pk, pk)
        action = request.POST.get("action", "save")
        subject_pk = document.subject_id
        if action == "archive":
            archive_document(document)
            messages.success(request, "Material archived.")
            if subject_pk:
                return _hub_redirect_after_upload(subject_pk, course_pk)
            return redirect("analytics_professor:materials_hub")
        if action == "restore":
            restore_document(document)
            messages.success(request, "Material restored.")
            return redirect(
                "analytics_professor:material_detail", course_pk=course_pk, pk=pk
            )
        subject = _resolve_upload_subject(
            self.course, request.user, request.POST.get("subject_id", "")
        )
        update_document_metadata(
            document,
            title=request.POST.get("title", document.title),
            material_type=request.POST.get("material_type", document.material_type),
            original_name=request.POST.get("original_name", document.original_name),
            subject=subject,
        )
        messages.success(request, "Material updated.")
        return redirect("analytics_professor:material_detail", course_pk=course_pk, pk=pk)


class MaterialDownloadView(ProfessorCourseMixin, View):
    """Authenticated download for a course learning material."""

    def get(self, request, course_pk, pk):
        document = get_object_or_404(
            LearningDocument.objects.filter(course_id=course_pk),
            pk=pk,
        )
        return _file_response(document)

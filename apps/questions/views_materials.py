"""Faculty content library views for learning materials."""

from __future__ import annotations

import mimetypes

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.ai.material_services import (
    SourceMaterialError,
    archive_document,
    document_download_name,
    documents_for_course,
    ingest_course_material,
    restore_document,
    update_document_metadata,
)
from apps.ai.models import LearningDocument
from apps.core.mixins import ProfessorCourseMixin
from apps.questions.views_professor import _subject_for_course


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


class MaterialListView(ProfessorCourseMixin, View):
    template_name = "professor/materials/list.html"

    def get(self, request, course_pk):
        include_archived = request.GET.get("archived") == "1"
        documents = documents_for_course(course_pk, include_archived=include_archived)
        subject = _subject_for_course(self.course)
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "active_tab": "materials",
                "documents": documents,
                "include_archived": include_archived,
                "subject": subject,
                "material_types": LearningDocument.MaterialType.choices,
                "library_count": documents.count(),
            },
        )


class MaterialUploadView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):
        uploaded = request.FILES.get("source_file")
        if not uploaded:
            messages.error(request, "Choose a file to upload.")
            return redirect("analytics_professor:material_list", course_pk=course_pk)
        title = request.POST.get("title", "").strip()
        material_type = request.POST.get(
            "material_type", LearningDocument.MaterialType.MODULE
        )
        subject = _subject_for_course(self.course)
        try:
            doc = ingest_course_material(
                uploaded_file=uploaded,
                course_id=self.course.pk,
                user=request.user,
                title=title,
                material_type=material_type,
                subject=subject,
            )
        except SourceMaterialError as exc:
            messages.error(request, str(exc))
            return redirect("analytics_professor:material_list", course_pk=course_pk)
        # Soft extraction warnings still leave the full file ready to download
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
                "material_types": LearningDocument.MaterialType.choices,
                "chunks_preview": document.chunks.order_by("order")[:5],
            },
        )

    def post(self, request, course_pk, pk):
        document = self.get_document(course_pk, pk)
        action = request.POST.get("action", "save")
        if action == "archive":
            archive_document(document)
            messages.success(request, "Material archived.")
            return redirect("analytics_professor:material_list", course_pk=course_pk)
        if action == "restore":
            restore_document(document)
            messages.success(request, "Material restored.")
            return redirect(
                "analytics_professor:material_detail", course_pk=course_pk, pk=pk
            )
        update_document_metadata(
            document,
            title=request.POST.get("title", document.title),
            material_type=request.POST.get("material_type", document.material_type),
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

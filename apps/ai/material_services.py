"""Faculty learning-material library helpers."""

from __future__ import annotations

from apps.ai.ingest import ingest_learning_upload
from apps.ai.models import LearningDocument
from apps.ai.source_extract import SourceMaterialError


def documents_for_course(course_id: int, *, include_archived: bool = False):
    qs = (
        LearningDocument.objects.filter(course_id=course_id)
        .select_related("subject", "created_by")
        .order_by("-created")
    )
    if not include_archived:
        qs = qs.filter(is_archived=False)
    return qs


def ready_documents_for_course(course_id: int):
    """Ready materials for a course, de-duplicated by display title (newest first)."""
    docs = list(
        documents_for_course(course_id).filter(status=LearningDocument.Status.READY)
    )
    seen: set[str] = set()
    unique: list[LearningDocument] = []
    for doc in docs:
        key = (doc.display_title or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def ingest_course_material(
    *,
    uploaded_file,
    course_id: int,
    user,
    title: str = "",
    material_type: str = LearningDocument.MaterialType.MODULE,
    subject=None,
) -> LearningDocument:
    """Upload + extract, then attach library metadata."""
    document = ingest_learning_upload(
        uploaded_file=uploaded_file,
        course_id=course_id,
        user=user,
    )
    document.title = (title or "").strip() or document.original_name
    if material_type in LearningDocument.MaterialType.values:
        document.material_type = material_type
    if subject is not None:
        document.subject = subject
    document.save(update_fields=["title", "material_type", "subject", "updated"])
    return document


def update_document_metadata(
    document: LearningDocument,
    *,
    title: str | None = None,
    material_type: str | None = None,
    subject=None,
    clear_subject: bool = False,
) -> LearningDocument:
    fields: list[str] = ["updated"]
    if title is not None:
        document.title = title.strip() or document.original_name
        fields.append("title")
    if material_type is not None and material_type in LearningDocument.MaterialType.values:
        document.material_type = material_type
        fields.append("material_type")
    if clear_subject:
        document.subject = None
        fields.append("subject")
    elif subject is not None:
        document.subject = subject
        fields.append("subject")
    document.save(update_fields=fields)
    return document


def set_document_subject(document: LearningDocument, subject) -> LearningDocument:
    document.subject = subject
    document.save(update_fields=["subject", "updated"])
    return document


def archive_document(document: LearningDocument) -> LearningDocument:
    document.is_archived = True
    document.save(update_fields=["is_archived", "updated"])
    return document


def restore_document(document: LearningDocument) -> LearningDocument:
    document.is_archived = False
    document.save(update_fields=["is_archived", "updated"])
    return document


def documents_for_subject(subject, *, include_archived: bool = False):
    """Materials linked to a subject (by subject FK or catalog course)."""
    from apps.reviews.exam_setup_services import course_for_subject

    course = course_for_subject(subject)
    from django.db.models import Q

    query = Q(subject=subject)
    if course is not None:
        query |= Q(course_id=course.pk)
    qs = (
        LearningDocument.objects.filter(query)
        .select_related("subject", "created_by")
        .distinct()
        .order_by("-created")
    )
    if not include_archived:
        qs = qs.filter(is_archived=False)
    return qs


def ready_documents_for_subject(subject):
    """Ready, non-archived materials for a subject (de-duplicated by title)."""
    docs = list(
        documents_for_subject(subject).filter(status=LearningDocument.Status.READY)
    )
    seen: set[str] = set()
    unique: list[LearningDocument] = []
    for doc in docs:
        key = (doc.display_title or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def document_download_name(document: LearningDocument) -> str:
    """Safe filename for Content-Disposition downloads."""
    name = (document.original_name or document.display_title or f"material-{document.pk}").strip()
    return name or f"material-{document.pk}"


__all__ = [
    "SourceMaterialError",
    "archive_document",
    "document_download_name",
    "documents_for_course",
    "documents_for_subject",
    "ingest_course_material",
    "ready_documents_for_course",
    "ready_documents_for_subject",
    "restore_document",
    "set_document_subject",
    "update_document_metadata",
]

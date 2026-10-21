"""Faculty learning-material library helpers."""

from __future__ import annotations

import itertools
import logging

from apps.ai.ingest import ingest_learning_upload
from apps.ai.models import LearningChunk, LearningDocument
from apps.ai.source_extract import SourceMaterialError

# Guardrail so a stray paste cannot rewrite a whole corpus through the editor.
MAX_EDITABLE_CHARS = 400_000

logger = logging.getLogger(__name__)


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
    original_name: str = "",
    pages=None,
    extraction_error: str = "",
) -> LearningDocument:
    """Upload + extract, then attach library metadata.

    ``pages`` lets a caller that already extracted text (to gate on subject
    relevance) hand it over instead of paying for extraction twice.
    """
    kwargs = {}
    if pages is not None:
        kwargs["pages"] = pages
        kwargs["extraction_error"] = extraction_error
    document = ingest_learning_upload(
        uploaded_file=uploaded_file,
        course_id=course_id,
        user=user,
        **kwargs,
    )
    cleaned_name = (original_name or "").strip()
    if cleaned_name:
        document.original_name = cleaned_name
    document.title = (title or "").strip() or document.original_name
    if material_type in LearningDocument.MaterialType.values:
        document.material_type = material_type
    if subject is not None:
        document.subject = subject
    document.save(
        update_fields=["title", "material_type", "subject", "original_name", "updated"]
    )
    return document


def update_document_metadata(
    document: LearningDocument,
    *,
    title: str | None = None,
    material_type: str | None = None,
    original_name: str | None = None,
    subject=None,
    clear_subject: bool = False,
) -> LearningDocument:
    fields: list[str] = ["updated"]
    if original_name is not None:
        cleaned_name = original_name.strip()
        if cleaned_name:
            document.original_name = cleaned_name
            fields.append("original_name")
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


# Formats the editor can regenerate on download. PDF has no faithful HTML
# representation, so those keep serving the original upload.
TEXT_FILE_SUFFIXES = (".txt", ".md", ".csv")
DOCX_SUFFIX = ".docx"
_MIN_OVERLAP_CHARS = 20


def document_text_is_rewritable(document: LearningDocument) -> bool:
    """True when the download can be regenerated from the editor content."""
    name = (document.original_name or "").lower()
    if not name and getattr(document, "file", None):
        name = (getattr(document.file, "name", None) or "").lower()
    return name.endswith(TEXT_FILE_SUFFIXES) or name.endswith(DOCX_SUFFIX)


def document_editor_html(document: LearningDocument) -> str:
    """Editor HTML for a document, derived from plain text when absent.

    Documents uploaded before this field existed (and formats with no markup)
    still get a usable surface: the text is promoted to paragraphs.
    """
    from apps.ai.document_html import text_to_html

    if document.content_html.strip():
        return document.content_html
    return text_to_html(document_plain_text(document))


def document_plain_text(document: LearningDocument) -> str:
    """Full editable text for a document.

    Prefers the canonical ``source_text``; documents ingested before that field
    existed fall back to reassembling their chunks (stripping the chunking
    overlap so the result reads as the original prose).
    """
    if document.source_text:
        return document.source_text

    chunks = list(document.chunks.order_by("order"))
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0].text

    from apps.ai.source_extract import CHUNK_OVERLAP

    parts = [chunks[0].text]
    for previous, current in itertools.pairwise(chunks):
        overlap = _shared_overlap(previous.text, current.text, CHUNK_OVERLAP)
        parts.append(current.text[overlap:])
    return "".join(parts)


def _shared_overlap(previous: str, current: str, max_overlap: int) -> int:
    """Length of the suffix of ``previous`` repeated at the start of ``current``."""
    limit = min(len(previous), len(current), max_overlap)
    for size in range(limit, _MIN_OVERLAP_CHARS - 1, -1):
        if previous.endswith(current[:size]):
            return size
    return 0


def replace_document_content(
    document: LearningDocument,
    *,
    html: str | None = None,
    text: str | None = None,
    rewrite_file: bool = True,
) -> dict:
    """Replace a document's content, re-deriving chunks so AI sees the edit.

    Accepts editor HTML (preferred) and/or plain text. Returns a small result
    dict for the view layer to turn into messages. Raises
    ``SourceMaterialError`` for unusable input.
    """
    from apps.ai.document_html import (
        DocumentConversionError,
        html_to_text,
        sanitize_html,
        text_to_html,
    )

    clean_html = ""
    if html is not None:
        clean_html = sanitize_html(html)
        clean_text = html_to_text(clean_html)
    else:
        clean_text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    if not clean_text.strip():
        raise SourceMaterialError("Add some content before saving.")
    if len(clean_text) > MAX_EDITABLE_CHARS:
        raise SourceMaterialError(
            f"That is too long to edit here (limit {MAX_EDITABLE_CHARS:,} characters). "
            "Upload the document as a file instead."
        )

    if not clean_html:
        try:
            clean_html = text_to_html(clean_text)
        except DocumentConversionError:
            clean_html = ""

    from apps.ai.source_extract import chunk_pages

    chunks = chunk_pages([{"page": 1, "text": clean_text}])
    document.chunks.all().delete()
    LearningChunk.objects.bulk_create(
        [
            LearningChunk(
                document=document,
                order=item["order"],
                page_start=item["page_start"],
                page_end=item["page_end"],
                text=item["text"],
            )
            for item in chunks
        ]
    )

    document.source_text = clean_text
    document.content_html = clean_html
    document.chunk_count = len(chunks)
    document.page_count = 1
    document.status = LearningDocument.Status.READY
    document.error_message = ""
    document.save(
        update_fields=[
            "source_text",
            "content_html",
            "chunk_count",
            "page_count",
            "status",
            "error_message",
            "updated",
        ]
    )

    result = {
        "chunk_count": len(chunks),
        "file_updated": False,
        "file_kept_original": False,
    }

    if rewrite_file and document.file and document_text_is_rewritable(document):
        result["file_updated"] = _rewrite_download(document, clean_text, clean_html)
        result["file_kept_original"] = not result["file_updated"]
    elif document.file:
        result["file_kept_original"] = True

    return result


def _rewrite_download(document: LearningDocument, text: str, html: str) -> bool:
    """Regenerate the stored download so it matches what the editor shows."""
    import posixpath

    from django.core.files.base import ContentFile

    from apps.ai.document_html import DocumentConversionError

    name = (document.original_name or "").lower()
    if name.endswith(DOCX_SUFFIX):
        from apps.ai.document_html import html_to_docx_bytes

        try:
            payload = html_to_docx_bytes(html, title=document.display_title)
        except DocumentConversionError as exc:
            logger.warning("DOCX export failed for document %s: %s", document.pk, exc)
            return False
    else:
        payload = text.encode("utf-8")

    # Pass only the basename: FileField.save re-applies upload_to, so a
    # full storage path would nest the directory twice.
    stored_name = document.file.name if document.file else ""
    basename = (
        posixpath.basename(stored_name)
        or posixpath.basename(document.original_name or "")
        or "material.txt"
    )
    try:
        if document.file:
            document.file.delete(save=False)
        document.file.save(basename, ContentFile(payload), save=False)
        document.save(update_fields=["file", "updated"])
        return True
    except (OSError, ValueError):
        # The old bytes are already gone; leave the row consistent rather than
        # pointing downloads at a file that no longer exists.
        document.file = None
        try:
            document.save(update_fields=["file", "updated"])
        except Exception:  # pragma: no cover - best effort cleanup
            logger.exception("Could not clear stored file for document %s", document.pk)
        return False


def ensure_download_file(document: LearningDocument) -> bool:
    """Ensure a downloadable file exists, rebuilding from text when possible.

    Returns True when ``document.file`` is available after this call.
    """
    if document.file:
        try:
            # Touch storage so a stale path surfaces before the response.
            document.file.open("rb").close()
            return True
        except (FileNotFoundError, OSError, ValueError):
            document.file = None
            document.save(update_fields=["file", "updated"])

    if not document_text_is_rewritable(document):
        return False
    text = document_plain_text(document)
    if not text.strip():
        return False
    return _rewrite_download(document, text, document.content_html or "")


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
    "MAX_EDITABLE_CHARS",
    "SourceMaterialError",
    "archive_document",
    "document_download_name",
    "document_editor_html",
    "document_plain_text",
    "document_text_is_rewritable",
    "documents_for_course",
    "documents_for_subject",
    "ensure_download_file",
    "ingest_course_material",
    "ready_documents_for_course",
    "ready_documents_for_subject",
    "replace_document_content",
    "restore_document",
    "set_document_subject",
    "update_document_metadata",
]

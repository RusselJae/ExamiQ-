"""Ingest uploaded learning modules into stored chunks."""

from __future__ import annotations

from django.core.files.base import ContentFile

from apps.ai.models import LearningChunk, LearningDocument
from apps.ai.source_extract import (
    SourceMaterialError,
    chunk_pages,
    extract_pages_from_upload,
)

# Full multi-page documents are accepted; students download this original file
_ALLOWED_SUFFIXES = (".txt", ".md", ".csv", ".pdf", ".docx")


def ingest_learning_upload(
    *,
    uploaded_file,
    course_id: int,
    user,
) -> LearningDocument:
    """Persist the full original upload, then extract text for AI retrieval.

    The original file is always kept so students can download the complete
    multi-page document. Text extraction is best-effort: if OCR/parsing fails,
    the document stays READY for download with a warning on error_message.
    """
    original_name = getattr(uploaded_file, "name", "") or "module"
    lower_name = original_name.lower()
    if not lower_name.endswith(_ALLOWED_SUFFIXES):
        raise SourceMaterialError(
            "Unsupported file type. Upload a TXT, MD, CSV, DOCX, or PDF file."
        )

    document = LearningDocument.objects.create(
        course_id=course_id,
        created_by=user,
        original_name=original_name,
        status=LearningDocument.Status.PENDING,
    )
    try:
        # Read once and store the complete bytes — never a single-page slice
        raw = uploaded_file.read()
        if not raw:
            raise SourceMaterialError("Uploaded file is empty.")
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)

        document.file.save(original_name, ContentFile(raw), save=True)

        # Text chunks power AI generate; download uses document.file as-is
        try:
            pages = extract_pages_from_upload(uploaded_file)
            chunks = chunk_pages(pages)
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
            document.page_count = max((p["page"] for p in pages), default=0)
            document.chunk_count = len(chunks)
            document.status = LearningDocument.Status.READY
            document.error_message = ""
        except SourceMaterialError as exc:
            # Keep the full file downloadable even when AI text cannot be read
            document.page_count = 0
            document.chunk_count = 0
            document.status = LearningDocument.Status.READY
            document.error_message = (
                "Full file saved for download, but text could not be extracted "
                f"for AI use: {exc}"
            )

        document.save(
            update_fields=[
                "page_count",
                "chunk_count",
                "status",
                "error_message",
                "updated",
            ]
        )
        return document
    except SourceMaterialError as exc:
        # Hard failures (empty file, save issues flagged as SourceMaterialError)
        document.status = LearningDocument.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message", "updated"])
        raise
    except Exception as exc:
        document.status = LearningDocument.Status.FAILED
        document.error_message = "Failed to process learning material."
        document.save(update_fields=["status", "error_message", "updated"])
        raise SourceMaterialError(str(exc)) from exc

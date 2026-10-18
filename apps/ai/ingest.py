"""Ingest uploaded learning modules into stored chunks."""

from __future__ import annotations

import logging

from django.core.files.base import ContentFile

from apps.ai.models import LearningChunk, LearningDocument
from apps.ai.source_extract import (
    SourceMaterialError,
    chunk_pages,
    extract_pages_from_upload,
)

logger = logging.getLogger(__name__)

# Full multi-page documents are accepted; students download this original file.
# This is the single source of truth for uploads: it is also the exact set the
# text extractor understands, so every allowed upload can be chunked for AI.
_ALLOWED_SUFFIXES = (".txt", ".md", ".csv", ".pdf", ".docx")


def allowed_upload_suffixes() -> tuple[str, ...]:
    """Extensions accepted for learning-material uploads."""
    return _ALLOWED_SUFFIXES


def is_allowed_upload(name: str) -> bool:
    """True when ``name`` may be uploaded as a learning material."""
    return (name or "").lower().endswith(_ALLOWED_SUFFIXES)

# Sentinel: "no extraction attempted yet", so callers that already extracted
# (e.g. to gate on subject relevance) do not pay for OCR twice.
_EXTRACT_LATER = object()


def _editor_html(name: str, raw: bytes, extracted_text: str) -> str:
    """Best-effort editor HTML for an upload; never blocks ingestion."""
    from apps.ai.document_html import DocumentConversionError, html_from_upload

    try:
        return html_from_upload(name, raw, extracted_text=extracted_text)
    except DocumentConversionError as exc:
        logger.warning("Editor HTML unavailable for %s: %s", name, exc)
        return ""
    except (ValueError, KeyError, TypeError, OSError) as exc:
        logger.warning("Editor HTML conversion failed for %s: %s", name, exc)
        return ""


def ingest_learning_upload(
    *,
    uploaded_file,
    course_id: int,
    user,
    pages=_EXTRACT_LATER,
    extraction_error: str = "",
) -> LearningDocument:
    """Persist the full original upload, then extract text for AI retrieval.

    The original file is always kept so students can download the complete
    multi-page document. Text extraction is best-effort: if OCR/parsing fails,
    the document stays READY for download with a warning on error_message.

    Callers that already extracted ``pages`` (to run a relevance check first)
    can pass them in; pass ``pages=[]`` plus ``extraction_error`` when their own
    attempt failed, so extraction is not retried.
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
        extracted_text = ""
        try:
            if pages is _EXTRACT_LATER:
                pages = extract_pages_from_upload(uploaded_file)
                extraction_error = ""
            elif not pages:
                raise SourceMaterialError(
                    extraction_error
                    or "Could not extract enough text from that file."
                )

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
            extracted_text = "\n\n".join(p["text"] for p in pages)
            document.source_text = extracted_text
            document.status = LearningDocument.Status.READY
            document.error_message = ""
        except SourceMaterialError as exc:
            # Keep the full file downloadable even when AI text cannot be read
            document.page_count = 0
            document.chunk_count = 0
            document.source_text = ""
            document.status = LearningDocument.Status.READY
            document.error_message = (
                "Full file saved for download, but text could not be extracted "
                f"for AI use: {exc}"
            )

        # The editor surface is built from the file itself, not the extractor,
        # so short-but-valid documents still open in the editor.
        document.content_html = _editor_html(original_name, raw, extracted_text)

        # The legacy extractor rejects very short documents. If we still ended
        # up with editor HTML, backfill the plain text and chunks from it rather
        # than leaving the material unusable for AI.
        if not document.source_text and document.content_html:
            from apps.ai.document_html import html_to_text

            recovered = html_to_text(document.content_html).strip()
            if recovered:
                document.source_text = recovered
                recovered_chunks = chunk_pages([{"page": 1, "text": recovered}])
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
                        for item in recovered_chunks
                    ]
                )
                document.chunk_count = len(recovered_chunks)
                document.page_count = 1

        document.save(
            update_fields=[
                "page_count",
                "chunk_count",
                "source_text",
                "content_html",
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
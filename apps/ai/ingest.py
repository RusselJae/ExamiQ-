"""Ingest uploaded learning modules into stored chunks."""

from __future__ import annotations

from django.core.files.base import ContentFile

from apps.ai.models import LearningChunk, LearningDocument
from apps.ai.source_extract import (
    SourceMaterialError,
    chunk_pages,
    extract_pages_from_upload,
)


def ingest_learning_upload(
    *,
    uploaded_file,
    course_id: int,
    user,
) -> LearningDocument:
    """Persist upload, extract all pages, and store overlapping chunks."""
    original_name = getattr(uploaded_file, "name", "") or "module"
    document = LearningDocument.objects.create(
        course_id=course_id,
        created_by=user,
        original_name=original_name,
        status=LearningDocument.Status.PENDING,
    )
    try:
        raw = uploaded_file.read()
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        document.file.save(original_name, ContentFile(raw), save=True)
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
        document.status = LearningDocument.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message", "updated"])
        raise
    except Exception as exc:
        document.status = LearningDocument.Status.FAILED
        document.error_message = "Failed to process learning material."
        document.save(update_fields=["status", "error_message", "updated"])
        raise SourceMaterialError(str(exc)) from exc

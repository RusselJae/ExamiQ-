"""Persistent jobs for long-running AI work and learning-document RAG storage."""

from django.conf import settings
from django.db import models


class AIGenerationJob(models.Model):
    class JobType(models.TextChoices):
        QUESTION_GENERATE = "question_generate", "Question generate"
        EXPLANATION_GENERATE = "explanation_generate", "Explanation generate"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    job_type = models.CharField(
        max_length=40,
        choices=JobType.choices,
        default=JobType.QUESTION_GENERATE,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_generation_jobs",
    )
    course_id = models.PositiveIntegerField()
    topic_id = models.PositiveIntegerField()
    difficulty = models.CharField(max_length=20, blank=True, default="")
    count = models.PositiveSmallIntegerField(default=3)
    question_type = models.CharField(
        max_length=20,
        blank=True,
        default="mcq",
        help_text="Single question type for this generation job.",
    )
    source_material = models.TextField(
        blank=True,
        default="",
        help_text="Extracted text from faculty-uploaded learning material.",
    )
    learning_document = models.ForeignKey(
        "ai.LearningDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generation_jobs",
    )
    reference_stem = models.TextField(
        blank=True,
        default="",
        help_text="Existing question stem when regenerating a high-mistake item.",
    )
    reference_question_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Source question pk when regenerating from the edit screen.",
    )
    error_message = models.TextField(blank=True, default="")
    result = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI generation job"
        verbose_name_plural = "AI generation jobs"
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.job_type} #{self.pk} ({self.status})"


class LearningDocument(models.Model):
    """Faculty-uploaded learning module stored for chunked retrieval."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class MaterialType(models.TextChoices):
        MODULE = "module", "Module"
        REVIEWER = "reviewer", "Reviewer"
        RESOURCE = "resource", "Learning resource"
        EXAM_PRINT = "exam_print", "Printed examination material"

    course_id = models.PositiveIntegerField(db_index=True)
    subject = models.ForeignKey(
        "questions.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_documents",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_documents",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    material_type = models.CharField(
        max_length=20,
        choices=MaterialType.choices,
        default=MaterialType.MODULE,
    )
    original_name = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(upload_to="learning_modules/%Y/%m/", blank=True)
    source_text = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Canonical extracted text. Faculty edits land here; LearningChunk "
            "rows are re-derived from it so AI retrieval follows the edits."
        ),
    )
    content_html = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Editor-facing HTML (headings, lists, bold, images) derived from "
            "the upload. source_text stays the plain-text projection for AI."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_archived = models.BooleanField(default=False)
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Learning document"
        verbose_name_plural = "Learning documents"
        ordering = ["-created"]

    def __str__(self) -> str:
        return self.title or self.original_name or f"Document #{self.pk}"

    @property
    def display_title(self) -> str:
        return self.title or self.original_name or f"Document #{self.pk}"

    @property
    def suffix(self) -> str:
        """Lowercase file extension including the dot, e.g. ``.pdf``."""
        name = (self.original_name or self.file.name or "").lower()
        if "." not in name:
            return ""
        return name.rsplit(".", 1)[-1]

    @property
    def is_pdf(self) -> bool:
        """True for PDF uploads, which are view/download only for now."""
        return self.suffix == "pdf"

    @property
    def file_type_label(self) -> str:
        """Short uppercase extension label for library cards (PDF, DOCX, …)."""
        name = self.original_name or (self.file.name if self.file else "")
        if "." not in name:
            return "FILE"
        return name.rsplit(".", 1)[-1].upper()[:8] or "FILE"

    @property
    def file_size_bytes(self) -> int | None:
        if not self.file:
            return None
        try:
            return int(self.file.size)
        except (OSError, ValueError, TypeError):
            return None

    @property
    def is_editable_by_office(self) -> bool:
        """True when the file format is supported by ONLYOFFICE for editing."""
        from apps.ai.office_editor import is_editable
        return is_editable(self)

    @property
    def is_content_editable(self) -> bool:
        """True when faculty can open an editor for this file (office or text)."""
        from apps.ai.material_services import document_text_is_rewritable

        return self.is_editable_by_office or document_text_is_rewritable(self)


class LearningChunk(models.Model):
    """Text chunk from a learning document for topic-scoped retrieval."""

    document = models.ForeignKey(
        LearningDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    order = models.PositiveIntegerField(default=0)
    page_start = models.PositiveIntegerField(default=1)
    page_end = models.PositiveIntegerField(default=1)
    text = models.TextField()

    class Meta:
        verbose_name = "Learning chunk"
        verbose_name_plural = "Learning chunks"
        ordering = ["document_id", "order"]

    def __str__(self) -> str:
        return f"Chunk {self.order} (p{self.page_start}-{self.page_end})"

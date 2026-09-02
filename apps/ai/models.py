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

    course_id = models.PositiveIntegerField(db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_documents",
    )
    original_name = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(upload_to="learning_modules/%Y/%m/", blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
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
        return self.original_name or f"Document #{self.pk}"


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

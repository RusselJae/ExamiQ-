"""Persistent jobs for long-running AI work (question generation, etc.)."""

from django.conf import settings
from django.db import models


class AIGenerationJob(models.Model):
    class JobType(models.TextChoices):
        QUESTION_GENERATE = "question_generate", "Question generate"

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

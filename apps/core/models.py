"""Shared core models."""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Department-scoped activity trail for chairperson oversight."""

    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        ASSIGNMENT_CREATE = "assignment_create", "Assignment created"
        ASSIGNMENT_DELETE = "assignment_delete", "Assignment deleted"
        QUESTION_CREATE = "question_create", "Question created"
        QUESTION_UPDATE = "question_update", "Question updated"
        QUESTION_TOGGLE = "question_toggle", "Question active toggled"
        SESSION_START = "session_start", "Exam session started"
        SESSION_COMPLETE = "session_complete", "Exam session completed"
        USER_APPROVE = "user_approve", "User approved"
        USER_REJECT = "user_reject", "User rejected"
        EXAM_SETUP_SAVE = "exam_setup_save", "Exam setup saved"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_role = models.CharField(max_length=32, blank=True)
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events_about",
    )
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action}: {self.message[:60]}"

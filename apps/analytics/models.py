from django.db import models

from apps.questions.models import Question, Topic
from apps.reviews.models import Answer
from apps.users.models import User


class ErrorType(models.Model):
    slug = models.SlugField(unique=True)
    label = models.CharField(max_length=100)
    category = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Error Type"
        verbose_name_plural = "Error Types"
        ordering = ["category", "label"]

    def __str__(self) -> str:
        return self.label


class MistakeRecord(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mistake_records",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="mistake_records",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="mistake_records",
    )
    answer = models.OneToOneField(
        Answer,
        on_delete=models.CASCADE,
        related_name="mistake_record",
    )
    error_type = models.ForeignKey(
        ErrorType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mistake_records",
    )
    ai_feedback = models.TextField(blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mistake Record"
        verbose_name_plural = "Mistake Records"
        ordering = ["-occurred_at"]

    def __str__(self) -> str:
        return f"Mistake by {self.student.email} on {self.topic.name}"

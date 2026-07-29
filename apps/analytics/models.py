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
    student_note = models.TextField(blank=True)
    student_image = models.ImageField(
        upload_to="mistake_concerns/%Y/%m/",
        blank=True,
        null=True,
    )
    faculty_note = models.TextField(blank=True)
    faculty_noted_at = models.DateTimeField(null=True, blank=True)
    faculty_viewed_at = models.DateTimeField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mistake Record"
        verbose_name_plural = "Mistake Records"
        ordering = ["-occurred_at"]

    def __str__(self) -> str:
        return f"Mistake by {self.student.email} on {self.topic.name}"

    @property
    def needs_faculty_reply(self) -> bool:
        from apps.analytics.concern_services import concern_needs_faculty_reply

        return concern_needs_faculty_reply(self)

    @property
    def latest_concern_image(self):
        from apps.analytics.concern_services import latest_concern_message

        latest = latest_concern_message(self)
        if latest and latest.image:
            return latest.image
        return self.student_image


class MistakeConcernMessage(models.Model):
    """Threaded student–faculty message on a mistake concern."""

    mistake_record = models.ForeignKey(
        MistakeRecord,
        on_delete=models.CASCADE,
        related_name="concern_messages",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="concern_messages",
    )
    body = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="mistake_concerns/%Y/%m/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mistake Concern Message"
        verbose_name_plural = "Mistake Concern Messages"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Concern message by {self.author.email} on mistake {self.mistake_record_id}"

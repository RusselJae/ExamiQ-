from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from model_utils.models import TimeStampedModel

from apps.questions.models import Question, QuestionChoice, Subject, Topic
from apps.users.models import Course, User


class ReviewWindow(TimeStampedModel):
    class ExamType(models.TextChoices):
        MIDTERM = "midterm", "Midterm"
        FINAL = "final", "Final"
        CUSTOM = "custom", "Custom"

    class Mode(models.TextChoices):
        TIMED_EXAM = "timed_exam", "Timed Exam"
        PRACTICE_REVIEW = "practice_review", "Practice Review"

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="review_windows",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_review_windows",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )
    title = models.CharField(max_length=200)
    exam_type = models.CharField(max_length=20, choices=ExamType.choices, default=ExamType.CUSTOM)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    topics = models.ManyToManyField(Topic, blank=True, related_name="review_windows")
    allowed_difficulties = models.JSONField(default=list)
    duration_minutes = models.PositiveIntegerField(default=30)
    seconds_per_question = models.PositiveIntegerField(
        default=30,
        help_text="Time limit per question in timed exam mode.",
    )
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.TIMED_EXAM,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Review Window"
        verbose_name_plural = "Review Windows"
        ordering = ["-opens_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.course.code})"

    @property
    def is_open(self) -> bool:
        now = timezone.now()
        return self.is_active and self.opens_at <= now <= self.closes_at

    def clean(self) -> None:
        if self.closes_at <= self.opens_at:
            raise ValidationError("Close time must be after open time.")


DEFAULT_EXAM_DIFFICULTIES = [
    Question.Difficulty.EASY,
    Question.Difficulty.MEDIUM,
    Question.Difficulty.HARD,
]


class ExamSetup(TimeStampedModel):
    """Faculty-controlled exam availability for a course offering."""

    course = models.OneToOneField(
        Course,
        on_delete=models.CASCADE,
        related_name="exam_setup",
    )
    is_enabled = models.BooleanField(default=True)
    topics = models.ManyToManyField(Topic, blank=True, related_name="exam_setups")
    allowed_difficulties = models.JSONField(default=list)
    duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Total exam session length in minutes.",
    )
    seconds_per_question = models.PositiveIntegerField(
        default=30,
        help_text="Time limit per question in timed exam mode.",
    )

    class Meta:
        verbose_name = "Exam Setup"
        verbose_name_plural = "Exam Setups"

    def __str__(self) -> str:
        return f"Exam setup for {self.course.code}"

    def save(self, *args, **kwargs):
        if not self.allowed_difficulties:
            self.allowed_difficulties = list(DEFAULT_EXAM_DIFFICULTIES)
        super().save(*args, **kwargs)

    def effective_difficulties(self) -> list[str]:
        return self.allowed_difficulties or list(DEFAULT_EXAM_DIFFICULTIES)

    def allowed_topic_queryset(self):
        subject = Subject.objects.filter(
            code=self.course.code,
            program=self.course.program,
        ).first()
        base = Topic.objects.filter(subject=subject, parent__isnull=True) if subject else Topic.objects.none()
        if self.topics.exists():
            return base.filter(pk__in=self.topics.values_list("pk", flat=True))
        return base


class ReviewSession(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"

    class Mode(models.TextChoices):
        TIMED_EXAM = "timed_exam", "Timed Exam"
        PRACTICE_REVIEW = "practice_review", "Practice Review"

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="review_sessions",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_sessions",
    )
    review_window = models.ForeignKey(
        ReviewWindow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="review_sessions",
    )
    difficulty = models.CharField(
        max_length=10,
        choices=Question.Difficulty.choices,
    )
    duration_minutes = models.PositiveSmallIntegerField(default=15)
    seconds_per_question = models.PositiveIntegerField(default=30)
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.TIMED_EXAM,
    )
    planned_question_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    pre_session_confidence = models.CharField(max_length=20, blank=True, default="")
    session_goal = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Review Session"
        verbose_name_plural = "Review Sessions"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.student.email} - {self.topic.name} ({self.status})"

    @property
    def expires_at(self):
        return self.started_at + timezone.timedelta(minutes=self.duration_minutes)

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def remaining_seconds(self) -> int:
        remaining = (self.expires_at - timezone.now()).total_seconds()
        return max(0, int(remaining))

    @property
    def total_questions(self) -> int:
        return self.answers.count()

    @property
    def correct_count(self) -> int:
        return self.answers.filter(is_correct=True).count()

    @property
    def accuracy(self) -> float:
        total = self.total_questions
        if total == 0:
            return 0.0
        return round(self.correct_count / total * 100, 1)


class Answer(TimeStampedModel):
    session = models.ForeignKey(
        ReviewSession,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    selected_choice = models.ForeignKey(
        QuestionChoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answers",
    )
    numeric_response = models.CharField(max_length=100, blank=True)
    confidence = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Student confidence level from 1 (low) to 5 (high).",
    )
    is_correct = models.BooleanField()
    timed_out = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Answer"
        verbose_name_plural = "Answers"
        ordering = ["answered_at"]
        unique_together = [["session", "question"]]
        constraints = [
            models.CheckConstraint(
                condition=Q(confidence__isnull=True)
                | (Q(confidence__gte=1) & Q(confidence__lte=5)),
                name="answer_confidence_range",
            ),
        ]

    def __str__(self) -> str:
        result = "correct" if self.is_correct else "incorrect"
        return f"Answer to Q#{self.question_id} ({result})"


class FeedbackView(models.Model):
    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name="feedback_views",
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Feedback View"
        verbose_name_plural = "Feedback Views"
        ordering = ["-viewed_at"]

    def __str__(self) -> str:
        return f"Feedback view for Answer #{self.answer_id}"


class StepFeedbackView(models.Model):
    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name="step_feedback_views",
    )
    explanation_step = models.ForeignKey(
        "questions.ExplanationStep",
        on_delete=models.CASCADE,
        related_name="step_feedback_views",
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Step Feedback View"
        verbose_name_plural = "Step Feedback Views"
        ordering = ["-viewed_at"]

    def __str__(self) -> str:
        return f"Step view for Answer #{self.answer_id} step #{self.explanation_step_id}"

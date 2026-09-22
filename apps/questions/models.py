from decimal import Decimal

from django.conf import settings
from django.db import models
from model_utils.models import TimeStampedModel

from apps.users.models import Program


class YearLevel(models.Model):
    order = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Year Level"
        verbose_name_plural = "Year Levels"
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name


class Subject(TimeStampedModel):
    class Semester(models.IntegerChoices):
        FIRST = 1, "1st Semester"
        SECOND = 2, "2nd Semester"
        MIDYEAR = 3, "Midyear"

    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    year_level = models.ForeignKey(
        YearLevel,
        on_delete=models.PROTECT,
        related_name="subjects",
    )
    semester = models.PositiveSmallIntegerField(choices=Semester.choices)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        ordering = ["program__name", "year_level__order", "semester", "code"]
        unique_together = [["program", "code"]]

    def __str__(self) -> str:
        return f"{self.code} – {self.name}"


class Topic(TimeStampedModel):
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="topics",
    )
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtopics",
    )

    class Meta:
        verbose_name = "Topic"
        verbose_name_plural = "Topics"
        ordering = ["subject__code", "name"]
        unique_together = [["subject", "name"]]

    def __str__(self) -> str:
        return f"{self.name} ({self.subject.code})"

    @property
    def program(self):
        return self.subject.program


class Question(TimeStampedModel):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Beginner"
        MEDIUM = "medium", "Intermediate"
        HARD = "hard", "Advanced"

    class QuestionType(models.TextChoices):
        MCQ = "mcq", "Multiple Choice"
        TRUE_FALSE = "true_false", "True or False"
        IDENTIFICATION = "identification", "Identification"
        ENUMERATION = "enumeration", "Enumeration"
        NUMERIC = "numeric", "Numeric Answer"

    # Faculty generation, exam setup, and create/edit pickers are MCQ-only.
    # Existing non-MCQ rows remain gradable; these are selection allowlists.
    AUTHORABLE_QUESTION_TYPES = frozenset({QuestionType.MCQ})
    AUTHORABLE_QUESTION_TYPE_CHOICES = [
        (QuestionType.MCQ, "Multiple Choice"),
    ]

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
    )
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.MCQ,
    )
    stem = models.TextField(help_text="Question text. Supports LaTeX with $...$ delimiters.")
    concept_tag = models.CharField(
        max_length=500,
        blank=True,
        help_text="Short concept label or AI-generated explanation summary.",
    )
    expected_answer = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Expected answer for True/False, Identification, or Enumeration. "
            "For Enumeration, put one item per line."
        ),
    )
    correct_answer = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Correct numeric answer (for numeric questions only).",
    )
    tolerance = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0.01"),
        help_text="Acceptable deviation for numeric answers.",
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposed_questions",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_questions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_note = models.TextField(blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_questions",
        help_text="Faculty member who attested this question as mathematically sound.",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    explanation_status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("faculty_approved", "Faculty approved"),
        ],
        default="draft",
        help_text="Whether step-by-step solutions are faculty-approved for students.",
    )
    faculty_feedback = models.TextField(
        blank=True,
        default="",
        help_text="Faculty review notes for high-mistake questions or validation.",
    )
    adaptive_explanation = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Faculty-curated adaptive explanation: what_went_wrong, why, "
            "quick_check, remember, worked_example, solution_steps."
        ),
    )

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ["topic__name", "difficulty"]

    def __str__(self) -> str:
        return f"{self.topic.name} [{self.difficulty}] ({self.get_question_type_display()})"

    @property
    def is_live(self) -> bool:
        return self.is_active and self.status == self.Status.APPROVED


class QuestionChoice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices",
    )
    label = models.CharField(max_length=1, help_text="A, B, C, or D")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    error_type = models.ForeignKey(
        "analytics.ErrorType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_choices",
    )

    class Meta:
        verbose_name = "Question Choice"
        verbose_name_plural = "Question Choices"
        ordering = ["label"]
        unique_together = [["question", "label"]]

    def __str__(self) -> str:
        return f"{self.label}: {self.text[:50]}"


class ExplanationStep(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="explanation_steps",
    )
    order = models.PositiveSmallIntegerField()
    content = models.TextField(help_text="Step-by-step explanation. Supports LaTeX.")
    professor_note = models.TextField(
        blank=True,
        help_text="Custom professor hint shown alongside this step.",
    )

    class Meta:
        verbose_name = "Explanation Step"
        verbose_name_plural = "Explanation Steps"
        ordering = ["order"]
        unique_together = [["question", "order"]]

    def __str__(self) -> str:
        return f"Step {self.order} for Q#{self.question_id}"


class QuestionValidationSession(models.Model):
    """Faculty random QA sample of bank questions for periodic checking."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    faculty = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="question_validation_sessions",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="validation_sessions",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_sessions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    size = models.PositiveSmallIntegerField(default=15)
    created = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Question validation session"
        verbose_name_plural = "Question validation sessions"
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"Validation #{self.pk} ({self.subject.code})"


class QuestionValidationItem(models.Model):
    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        OK = "ok", "OK"
        NEEDS_EDIT = "needs_edit", "Needs edit"
        UNPUBLISH = "unpublish", "Unpublish"

    session = models.ForeignKey(
        QuestionValidationSession,
        on_delete=models.CASCADE,
        related_name="items",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="validation_items",
    )
    order = models.PositiveSmallIntegerField(default=0)
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        default=Outcome.PENDING,
    )
    notes = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Question validation item"
        verbose_name_plural = "Question validation items"
        ordering = ["session_id", "order"]
        unique_together = [["session", "question"]]

    def __str__(self) -> str:
        return f"Item {self.order} Q#{self.question_id} ({self.outcome})"

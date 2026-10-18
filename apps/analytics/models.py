from django.db import models

from apps.questions.models import Question, Topic
from apps.reviews.models import Answer
from apps.users.models import User


class ConceptReview(models.Model):
    """Student progress on one concept after repeated exam misses."""

    class Status(models.TextChoices):
        NEEDS_REVIEW = "needs_review", "Needs Review"
        PRACTICING = "practicing", "Practicing"
        RESOLVED = "resolved", "Resolved"

    class DiagnosisType(models.TextChoices):
        MISCONCEPTION = "misconception", "Misconception"
        KNOWLEDGE_GAP = "knowledge_gap", "Knowledge Gap"
        CARELESS_ERROR = "careless_error", "Careless Error"

    class Step(models.TextChoices):
        LEARN = "learn", "Learn"
        TRY_IT = "try_it", "Try it"
        PRACTICE = "practice", "Practice"

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="concept_reviews",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    concept_key = models.CharField(max_length=200)
    concept_name = models.CharField(max_length=200)
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="concept_reviews",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEEDS_REVIEW,
        db_index=True,
    )
    current_step = models.CharField(
        max_length=20,
        choices=Step.choices,
        default=Step.LEARN,
    )
    diagnosis_type = models.CharField(
        max_length=20,
        choices=DiagnosisType.choices,
        blank=True,
        default="",
    )
    known_error_tags = models.JSONField(default=list, blank=True)
    correct_streak = models.PositiveSmallIntegerField(default=0)
    miss_count = models.PositiveIntegerField(default=0)
    same_wrong_answer_count = models.PositiveIntegerField(default=0)
    marked_sure_count = models.PositiveIntegerField(default=0)
    marked_guessing_count = models.PositiveIntegerField(default=0)
    last_wrong_answer_text = models.CharField(max_length=500, blank=True, default="")
    learn_payload = models.JSONField(default=dict, blank=True)
    feedback_styles_used = models.JSONField(default=list, blank=True)
    prerequisite_flag = models.CharField(max_length=200, blank=True, default="")
    prerequisite_mode = models.BooleanField(default=False)
    difficulty = models.CharField(max_length=20, blank=True, default="beginner")
    resolved_at = models.DateTimeField(null=True, blank=True)
    recheck_due_at = models.DateTimeField(null=True, blank=True)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Concept Review"
        verbose_name_plural = "Concept Reviews"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "concept_key"],
                name="analytics_conceptreview_student_concept_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(correct_streak__lte=3),
                name="analytics_conceptreview_streak_max_3",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.concept_name} ({self.student.email})"

    @property
    def try_it_payload(self) -> dict:
        payload = self.learn_payload or {}
        try_it = payload.get("try_it")
        return try_it if isinstance(try_it, dict) else {}


class ConceptPracticeAttempt(models.Model):
    """One AI-generated untimed practice question for a concept review."""

    concept_review = models.ForeignKey(
        ConceptReview,
        on_delete=models.CASCADE,
        related_name="practice_attempts",
    )
    attempt_number = models.PositiveIntegerField(default=1)
    question_payload = models.JSONField(default=dict)
    chosen_option_id = models.CharField(max_length=8, blank=True, default="")
    is_correct = models.BooleanField(null=True, blank=True)
    error_tag_hit = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Concept Practice Attempt"
        verbose_name_plural = "Concept Practice Attempts"
        ordering = ["attempt_number", "created_at"]

    def __str__(self) -> str:
        return (
            f"Practice #{self.attempt_number} for "
            f"{self.concept_review.concept_name}"
        )


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
    concern_faculty = models.ManyToManyField(
        User,
        blank=True,
        related_name="concern_mistake_records",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )

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


class StudentFacultyConversation(models.Model):
    """One shared chat thread per student with assigned faculty."""

    student = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="faculty_conversation",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    participating_faculty = models.ManyToManyField(
        User,
        blank=True,
        related_name="student_chat_conversations",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )

    class Meta:
        verbose_name = "Student Faculty Conversation"
        verbose_name_plural = "Student Faculty Conversations"
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self) -> str:
        return f"Chat with {self.student.email}"


class StudentFacultyMessage(models.Model):
    """Message in a student–faculty conversation thread."""

    conversation = models.ForeignKey(
        StudentFacultyConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="faculty_chat_messages",
    )
    body = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="faculty_chat/%Y/%m/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Student Faculty Message"
        verbose_name_plural = "Student Faculty Messages"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Chat message by {self.author.email} in conversation {self.conversation_id}"


class FacultyConversation(models.Model):
    """One DM thread between two professors (unordered pair, low/high PK)."""

    participant_low = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="faculty_conversations_as_low",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )
    participant_high = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="faculty_conversations_as_high",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Faculty Conversation"
        verbose_name_plural = "Faculty Conversations"
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["participant_low", "participant_high"],
                name="analytics_facultyconversation_unique_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(participant_low_id__lt=models.F("participant_high_id")),
                name="analytics_facultyconversation_low_lt_high",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Faculty chat {self.participant_low_id}–{self.participant_high_id}"
        )

    def other_participant(self, viewer: User) -> User:
        if viewer.pk == self.participant_low_id:
            return self.participant_high
        return self.participant_low


class FacultyMessage(models.Model):
    """Message in a faculty-to-faculty conversation thread."""

    conversation = models.ForeignKey(
        FacultyConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="faculty_peer_chat_messages",
    )
    body = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="faculty_peer_chat/%Y/%m/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Faculty Message"
        verbose_name_plural = "Faculty Messages"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return (
            f"Faculty message by {self.author.email} "
            f"in conversation {self.conversation_id}"
        )

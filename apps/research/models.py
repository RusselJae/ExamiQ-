from django.conf import settings
from django.db import models
from model_utils.models import TimeStampedModel


class PilotConsent(TimeStampedModel):
    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pilot_consent",
    )
    consented = models.BooleanField(default=False)
    consented_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Pilot Consent"
        verbose_name_plural = "Pilot Consents"

    def __str__(self) -> str:
        return f"Consent for {self.student.email}"


class SurveyResponse(TimeStampedModel):
    class SurveyType(models.TextChoices):
        PRE = "pre", "Pre-study"
        POST = "post", "Post-study"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="survey_responses",
    )
    survey_type = models.CharField(max_length=10, choices=SurveyType.choices)
    calibration_awareness = models.PositiveSmallIntegerField()
    confidence_rating_usefulness = models.PositiveSmallIntegerField()
    would_recommend = models.PositiveSmallIntegerField()
    open_feedback = models.TextField(blank=True)

    class Meta:
        verbose_name = "Survey Response"
        verbose_name_plural = "Survey Responses"
        unique_together = [["student", "survey_type"]]
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.get_survey_type_display()} — {self.student.email}"

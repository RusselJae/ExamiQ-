from django.contrib import admin

from apps.research.models import PilotConsent, SurveyResponse


@admin.register(PilotConsent)
class PilotConsentAdmin(admin.ModelAdmin):
    list_display = ["student", "consented", "consented_at", "created"]
    search_fields = ["student__email"]
    readonly_fields = ["created", "modified"]


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "survey_type",
        "calibration_awareness",
        "confidence_rating_usefulness",
        "would_recommend",
        "created",
    ]
    list_filter = ["survey_type"]
    search_fields = ["student__email"]
    readonly_fields = ["created", "modified"]

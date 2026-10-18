from django.contrib import admin

from apps.analytics.models import (
    ConceptPracticeAttempt,
    ConceptReview,
    ErrorType,
    FacultyConversation,
    FacultyMessage,
    MistakeConcernMessage,
    MistakeRecord,
    StudentFacultyConversation,
    StudentFacultyMessage,
)


@admin.register(ErrorType)
class ErrorTypeAdmin(admin.ModelAdmin):
    list_display = ["label", "slug", "category"]
    list_filter = ["category"]
    search_fields = ["label", "slug"]
    ordering = ["category", "label"]


class MistakeConcernMessageInline(admin.TabularInline):
    model = MistakeConcernMessage
    extra = 0
    readonly_fields = ["author", "body", "image", "created_at"]
    can_delete = False


@admin.register(MistakeRecord)
class MistakeRecordAdmin(admin.ModelAdmin):
    list_display = ["student", "topic", "question", "error_type", "occurred_at"]
    list_filter = ["topic__subject__program", "error_type", "occurred_at"]
    search_fields = ["student__email", "topic__name"]
    ordering = ["-occurred_at"]
    readonly_fields = ["occurred_at"]
    inlines = [MistakeConcernMessageInline]


class ConceptPracticeAttemptInline(admin.TabularInline):
    model = ConceptPracticeAttempt
    extra = 0
    readonly_fields = [
        "attempt_number",
        "chosen_option_id",
        "is_correct",
        "error_tag_hit",
        "created_at",
        "answered_at",
    ]
    can_delete = False


@admin.register(ConceptReview)
class ConceptReviewAdmin(admin.ModelAdmin):
    list_display = [
        "concept_name",
        "student",
        "status",
        "correct_streak",
        "miss_count",
        "updated_at",
    ]
    list_filter = ["status", "diagnosis_type"]
    search_fields = ["concept_name", "student__email", "concept_key"]
    ordering = ["-updated_at"]
    inlines = [ConceptPracticeAttemptInline]


class StudentFacultyMessageInline(admin.TabularInline):
    model = StudentFacultyMessage
    extra = 0
    readonly_fields = ["author", "body", "image", "created_at"]
    can_delete = False


@admin.register(StudentFacultyConversation)
class StudentFacultyConversationAdmin(admin.ModelAdmin):
    list_display = ["student", "last_message_at", "created_at"]
    search_fields = ["student__email", "student__first_name", "student__last_name"]
    filter_horizontal = ["participating_faculty"]
    inlines = [StudentFacultyMessageInline]
    ordering = ["-last_message_at", "-created_at"]


class FacultyMessageInline(admin.TabularInline):
    model = FacultyMessage
    extra = 0
    readonly_fields = ["author", "body", "image", "created_at"]
    can_delete = False


@admin.register(FacultyConversation)
class FacultyConversationAdmin(admin.ModelAdmin):
    list_display = ["participant_low", "participant_high", "last_message_at", "created_at"]
    search_fields = [
        "participant_low__email",
        "participant_high__email",
    ]
    inlines = [FacultyMessageInline]
    ordering = ["-last_message_at", "-created_at"]

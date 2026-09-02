from django.contrib import admin

from apps.analytics.models import (
    ErrorType,
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

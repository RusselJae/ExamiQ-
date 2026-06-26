from django.contrib import admin

from apps.analytics.models import ErrorType, MistakeRecord


@admin.register(ErrorType)
class ErrorTypeAdmin(admin.ModelAdmin):
    list_display = ["label", "slug", "category"]
    list_filter = ["category"]
    search_fields = ["label", "slug"]
    ordering = ["category", "label"]


@admin.register(MistakeRecord)
class MistakeRecordAdmin(admin.ModelAdmin):
    list_display = ["student", "topic", "question", "error_type", "occurred_at"]
    list_filter = ["topic__subject__program", "error_type", "occurred_at"]
    search_fields = ["student__email", "topic__name"]
    ordering = ["-occurred_at"]
    readonly_fields = ["occurred_at"]

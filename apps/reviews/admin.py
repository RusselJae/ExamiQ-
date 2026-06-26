from django.contrib import admin

from apps.reviews.models import Answer, FeedbackView, ReviewSession, ReviewWindow, StepFeedbackView


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ["question", "is_correct", "confidence", "answered_at"]
    can_delete = False


@admin.register(ReviewSession)
class ReviewSessionAdmin(admin.ModelAdmin):
    list_display = ["student", "topic", "difficulty", "status", "started_at", "accuracy"]
    list_filter = ["status", "difficulty", "topic"]
    search_fields = ["student__email", "topic__name"]
    ordering = ["-started_at"]
    inlines = [AnswerInline]
    readonly_fields = ["started_at", "ended_at"]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["session", "question", "is_correct", "confidence", "answered_at"]
    list_filter = ["is_correct", "confidence"]
    search_fields = ["session__student__email"]
    ordering = ["-answered_at"]


@admin.register(FeedbackView)
class FeedbackViewAdmin(admin.ModelAdmin):
    list_display = ["answer", "viewed_at"]
    ordering = ["-viewed_at"]


@admin.register(ReviewWindow)
class ReviewWindowAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "opens_at", "closes_at", "is_active"]
    list_filter = ["is_active", "exam_type", "course"]
    search_fields = ["title", "course__code"]
    filter_horizontal = ["topics"]


@admin.register(StepFeedbackView)
class StepFeedbackViewAdmin(admin.ModelAdmin):
    list_display = ["answer", "explanation_step", "viewed_at"]
    ordering = ["-viewed_at"]

from django.contrib import admin

from apps.questions.models import ExplanationStep, Question, QuestionChoice, Subject, Topic, YearLevel


class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    extra = 4
    fields = ["label", "text", "is_correct"]


class ExplanationStepInline(admin.TabularInline):
    model = ExplanationStep
    extra = 3
    fields = ["order", "content"]


@admin.register(YearLevel)
class YearLevelAdmin(admin.ModelAdmin):
    list_display = ["order", "name"]
    ordering = ["order"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "program", "year_level", "semester"]
    list_filter = ["program", "year_level", "semester"]
    search_fields = ["code", "name"]
    ordering = ["program__name", "year_level__order", "code"]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ["name", "subject", "parent"]
    list_filter = ["subject__program", "subject__year_level"]
    search_fields = ["name", "subject__code"]
    ordering = ["subject__code", "name"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["id", "topic", "difficulty", "question_type", "status", "is_active"]
    list_filter = ["difficulty", "question_type", "topic__subject__program", "status", "is_active"]
    search_fields = ["stem", "topic__name", "concept_tag"]
    ordering = ["topic__name", "difficulty"]
    inlines = [QuestionChoiceInline, ExplanationStepInline]
    fieldsets = (
        (None, {"fields": ("topic", "difficulty", "question_type", "stem", "concept_tag", "status", "is_active")}),
        ("Review", {"fields": ("proposed_by", "reviewed_by", "reviewed_at", "rejection_note")}),
        (
            "Numeric Answer Settings",
            {
                "fields": ("correct_answer", "tolerance"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(QuestionChoice)
class QuestionChoiceAdmin(admin.ModelAdmin):
    list_display = ["question", "label", "is_correct"]
    list_filter = ["is_correct"]
    search_fields = ["text", "question__stem"]


@admin.register(ExplanationStep)
class ExplanationStepAdmin(admin.ModelAdmin):
    list_display = ["question", "order"]
    list_filter = ["question__topic"]
    ordering = ["question", "order"]

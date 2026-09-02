from django import forms
from django.utils import timezone

from apps.questions.models import Question, Subject, Topic
from apps.reviews.models import (
    DEFAULT_EXAM_DIFFICULTIES,
    ExamSetup,
    ProgramExamSetup,
    ReviewWindow,
    SectionExamSetup,
)
from apps.users.models import User as AuthUser

FORM_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)


class ExamSetupForm(forms.ModelForm):
    topics = forms.ModelMultipleChoiceField(
        queryset=Topic.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "exam-setup-topic-grid"}),
        help_text="Leave empty to allow all topics for this subject.",
    )
    allowed_difficulties = forms.MultipleChoiceField(
        choices=Question.Difficulty.choices,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "exam-setup-topic-grid"}),
        initial=list(DEFAULT_EXAM_DIFFICULTIES),
    )

    class Meta:
        model = ExamSetup
        fields = [
            "is_enabled",
            "seconds_per_question",
            "topics",
            "allowed_difficulties",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "seconds_per_question": forms.NumberInput(attrs={"class": FORM_INPUT_CLASS, "min": 10, "max": 120}),
        }
        labels = {
            "seconds_per_question": "Time per question (seconds)",
        }
        help_texts = {
            "seconds_per_question": "How long students have to answer each question.",
        }

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course:
            self.fields["topics"].queryset = Topic.objects.filter(
                subject__program=course.program,
                subject__code=course.code,
                parent__isnull=True,
            ).order_by("name")

    def clean(self):
        cleaned = super().clean()
        seconds = cleaned.get("seconds_per_question")
        if seconds is not None and not 10 <= seconds <= 120:
            raise forms.ValidationError("Seconds per question must be between 10 and 120.")
        difficulties = cleaned.get("allowed_difficulties")
        if not difficulties:
            raise forms.ValidationError("Select at least one difficulty level.")
        return cleaned

    def clean_allowed_difficulties(self):
        difficulties = self.cleaned_data.get("allowed_difficulties")
        if not difficulties:
            raise forms.ValidationError("Select at least one difficulty level.")
        return difficulties


class ReviewWindowForm(forms.ModelForm):
    topics = forms.ModelMultipleChoiceField(
        queryset=Topic.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave empty to allow all topics in the program.",
    )
    allowed_difficulties = forms.MultipleChoiceField(
        choices=Question.Difficulty.choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[Question.Difficulty.EASY, Question.Difficulty.MEDIUM, Question.Difficulty.HARD],
    )

    class Meta:
        model = ReviewWindow
        fields = [
            "title",
            "exam_type",
            "opens_at",
            "closes_at",
            "topics",
            "allowed_difficulties",
            "duration_minutes",
            "seconds_per_question",
            "mode",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": FORM_INPUT_CLASS}),
            "exam_type": forms.Select(attrs={"class": FORM_INPUT_CLASS}),
            "opens_at": forms.DateTimeInput(
                attrs={"class": FORM_INPUT_CLASS, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "closes_at": forms.DateTimeInput(
                attrs={"class": FORM_INPUT_CLASS, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "duration_minutes": forms.NumberInput(attrs={"class": FORM_INPUT_CLASS}),
            "seconds_per_question": forms.NumberInput(attrs={"class": FORM_INPUT_CLASS}),
            "mode": forms.Select(attrs={"class": FORM_INPUT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
        }

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course and course.program_id:
            self.fields["topics"].queryset = Topic.objects.filter(subject__program=course.program)

    def clean(self):
        cleaned = super().clean()
        opens_at = cleaned.get("opens_at")
        closes_at = cleaned.get("closes_at")
        if opens_at and closes_at and closes_at <= opens_at:
            raise forms.ValidationError("Close time must be after open time.")
        duration = cleaned.get("duration_minutes")
        if duration is not None and not 5 <= duration <= 120:
            raise forms.ValidationError("Duration must be between 5 and 120 minutes.")
        seconds = cleaned.get("seconds_per_question")
        if seconds is not None and not 10 <= seconds <= 120:
            raise forms.ValidationError("Seconds per question must be between 10 and 120.")
        difficulties = cleaned.get("allowed_difficulties")
        if not difficulties:
            raise forms.ValidationError("Select at least one difficulty level.")
        return cleaned

    def clean_topics(self):
        topics = self.cleaned_data.get("topics")
        return topics


def get_open_windows_for_student(student):
    """Return active review windows for all non-archived course offerings."""
    now = timezone.now()
    return (
        ReviewWindow.objects.filter(
            is_active=True,
            opens_at__lte=now,
            closes_at__gte=now,
            course__is_archived=False,
        )
        .select_related("course", "course__program", "course__professor")
        .prefetch_related("topics")
        .distinct()
        .order_by("closes_at")
    )


class ProgramExamSetupForm(forms.ModelForm):
    """Faculty configures program-wide exam availability for all students."""

    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_INPUT_CLASS,
                "id": "id_program_exam_subjects",
                "size": "8",
            }
        ),
        label="Course subjects available for exams",
        help_text="Students pick at least 1 from this list. Leave empty to allow the full BSED Math catalog.",
    )
    allowed_difficulties = forms.MultipleChoiceField(
        choices=Question.Difficulty.choices,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "exam-setup-topic-grid"}),
        initial=list(DEFAULT_EXAM_DIFFICULTIES),
        required=False,
    )

    class Meta:
        model = ProgramExamSetup
        fields = [
            "is_enabled",
            "seconds_per_question",
            "subjects",
            "allowed_difficulties",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "seconds_per_question": forms.NumberInput(
                attrs={"class": FORM_INPUT_CLASS, "min": 10, "max": 120}
            ),
        }
        labels = {
            "seconds_per_question": "Time per question (seconds)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subjects"].queryset = (
            Subject.objects.filter(program__slug=AuthUser.HomeDegreeProgram.BSED_MATH)
            .select_related("year_level")
            .order_by("year_level__order", "semester", "code")
        )
        self.fields["subjects"].label_from_instance = (
            lambda obj: f"{obj.code} — {obj.name}"
        )
        if self.instance and self.instance.pk:
            self.fields["subjects"].initial = self.instance.subjects.all()

    def clean_seconds_per_question(self):
        seconds = self.cleaned_data.get("seconds_per_question")
        if seconds is not None and not 10 <= seconds <= 120:
            raise forms.ValidationError("Seconds per question must be between 10 and 120.")
        return seconds

    def clean_allowed_difficulties(self):
        difficulties = self.cleaned_data.get("allowed_difficulties")
        if not difficulties:
            return list(DEFAULT_EXAM_DIFFICULTIES)
        return difficulties


class SectionExamSetupForm(forms.ModelForm):
    """Faculty configures which courses a section may take for exams."""

    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_INPUT_CLASS,
                "id": "id_section_exam_subjects",
                "size": "8",
            }
        ),
        label="Courses available for exams",
        help_text="Students in this section pick at least 1 from this list.",
    )
    allowed_difficulties = forms.MultipleChoiceField(
        choices=Question.Difficulty.choices,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "exam-setup-topic-grid"}),
        initial=list(DEFAULT_EXAM_DIFFICULTIES),
        required=False,
    )

    class Meta:
        model = SectionExamSetup
        fields = [
            "is_enabled",
            "seconds_per_question",
            "subjects",
            "allowed_difficulties",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "seconds_per_question": forms.NumberInput(
                attrs={"class": FORM_INPUT_CLASS, "min": 10, "max": 120}
            ),
        }
        labels = {
            "seconds_per_question": "Fallback time per question (seconds)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subjects"].queryset = (
            Subject.objects.filter(program__slug=AuthUser.HomeDegreeProgram.BSED_MATH)
            .select_related("year_level")
            .order_by("year_level__order", "semester", "code")
        )
        self.fields["subjects"].label_from_instance = (
            lambda obj: f"{obj.code} — {obj.name}"
        )
        if self.instance and self.instance.pk:
            self.fields["subjects"].initial = self.instance.subjects.all()

    def clean_seconds_per_question(self):
        seconds = self.cleaned_data.get("seconds_per_question")
        if seconds is not None and not 10 <= seconds <= 120:
            raise forms.ValidationError("Seconds per question must be between 10 and 120.")
        return seconds

    def clean_allowed_difficulties(self):
        difficulties = self.cleaned_data.get("allowed_difficulties")
        if not difficulties:
            return list(DEFAULT_EXAM_DIFFICULTIES)
        return difficulties

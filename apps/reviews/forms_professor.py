from django import forms
from django.utils import timezone

from apps.questions.models import Question, Topic
from apps.reviews.models import ReviewWindow

FORM_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)


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

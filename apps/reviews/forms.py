from django import forms

from apps.questions.curriculum import subject_queryset_for_student
from apps.questions.models import Question, Subject, Topic
from apps.questions.services import count_available_questions
from apps.reviews.models import ReviewWindow
from apps.users.models import Course, User

FORM_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)

PILOT_DIFFICULTY_CHOICES = [
    (Question.Difficulty.EASY, "Beginner"),
    (Question.Difficulty.MEDIUM, "Intermediate"),
    (Question.Difficulty.HARD, "Advanced"),
]


class ReviewSetupForm(forms.Form):
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(),
        label="Subject",
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_subject"}),
    )
    topic = forms.ModelChoiceField(
        queryset=Topic.objects.none(),
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_topic"}),
    )
    review_window = forms.ModelChoiceField(
        queryset=ReviewWindow.objects.none(),
        required=False,
        empty_label="Free practice (no scheduled window)",
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS}),
    )
    difficulty = forms.ChoiceField(
        choices=PILOT_DIFFICULTY_CHOICES,
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS}),
    )
    duration_minutes = forms.IntegerField(
        min_value=5,
        max_value=120,
        initial=30,
        widget=forms.NumberInput(attrs={"class": FORM_INPUT_CLASS}),
    )

    def __init__(self, *args, student=None, open_windows=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        if student:
            self.fields["subject"].queryset = subject_queryset_for_student(student)
        if open_windows is not None:
            self.fields["review_window"].queryset = open_windows

        subject = None
        if self.data.get("subject"):
            try:
                subject = Subject.objects.get(pk=self.data["subject"])
            except (Subject.DoesNotExist, ValueError, KeyError):
                pass
        elif self.initial.get("subject"):
            subject = self.initial["subject"]
        if subject:
            self.fields["topic"].queryset = Topic.objects.filter(
                subject=subject, parent__isnull=True
            ).order_by("name")

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get("subject")
        window = cleaned.get("review_window")
        topic = cleaned.get("topic")
        difficulty = cleaned.get("difficulty")

        if self.student and self.student.role == User.Role.STUDENT:
            if not self.student.home_degree_program:
                raise forms.ValidationError(
                    "Set your home degree program in Profile before starting an exam."
                )
            if not self.student.year_level_id:
                raise forms.ValidationError(
                    "Set your year level in Profile before starting an exam."
                )

        if subject and topic and topic.subject_id != subject.pk:
            raise forms.ValidationError("Selected topic does not belong to this subject.")

        if window:
            if not window.is_open:
                raise forms.ValidationError("This review window is no longer open.")
            if window.topics.exists() and topic and topic not in window.topics.all():
                raise forms.ValidationError("Selected topic is not allowed for this review window.")
            if difficulty and difficulty not in window.allowed_difficulties:
                raise forms.ValidationError("Selected difficulty is not allowed for this review window.")
            cleaned["duration_minutes"] = window.duration_minutes

        if topic and difficulty:
            available = count_available_questions(topic, difficulty)
            if available == 0:
                raise forms.ValidationError(
                    "No approved questions for this topic and difficulty. "
                    "Try another topic or difficulty."
                )
        return cleaned

    def get_course_for_session(self):
        subject = self.cleaned_data.get("subject")
        window = self.cleaned_data.get("review_window")
        if window:
            return window.course
        if subject:
            return (
                Course.objects.filter(program=subject.program, is_archived=False)
                .order_by("-academic_year", "term", "code")
                .first()
            )
        return None


class AnswerForm(forms.Form):
    CONFIDENCE_CHOICES = [(i, str(i)) for i in range(1, 6)]

    confidence = forms.ChoiceField(
        choices=CONFIDENCE_CHOICES,
        required=False,
        widget=forms.HiddenInput(attrs={"id": "confidence-input"}),
    )
    numeric_response = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "w-full rounded-lg border-gray-300", "placeholder": "Enter your answer"}),
    )
    selected_choice = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.RadioSelect,
    )
    timed_out = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def clean_confidence(self):
        confidence = self.cleaned_data.get("confidence")
        if not confidence:
            return None
        valid = {str(c[0]) for c in self.CONFIDENCE_CHOICES}
        if confidence not in valid:
            raise forms.ValidationError("Please select a confidence level.")
        return confidence

    def __init__(self, *args, question=None, timed_exam=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.timed_exam = timed_exam
        if question:
            if question.question_type == Question.QuestionType.MCQ:
                self.fields["selected_choice"].queryset = question.choices.all()
                del self.fields["numeric_response"]
            else:
                del self.fields["selected_choice"]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("timed_out"):
            return cleaned
        if not cleaned.get("confidence"):
            raise forms.ValidationError("Please select your confidence level.")
        if not cleaned.get("selected_choice") and not cleaned.get("numeric_response"):
            if "selected_choice" in self.fields or "numeric_response" in self.fields:
                raise forms.ValidationError("Please select an answer.")
        return cleaned

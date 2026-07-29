from django import forms

from apps.questions.models import Question, Subject
from apps.reviews.exam_setup_services import (
    MIN_EXAM_SUBJECTS,
    build_multi_subject_exam_target,
    student_setup_eligibility,
    subjects_available_for_student,
)

FORM_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)

FORM_MULTISELECT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition "
    "min-h-[10rem]"
)

PILOT_DIFFICULTY_CHOICES = [
    (Question.Difficulty.EASY, "Beginner"),
    (Question.Difficulty.MEDIUM, "Intermediate"),
    (Question.Difficulty.HARD, "Advanced"),
]

PRE_SESSION_CONFIDENCE_CHOICES = [
    ("not_confident", "Not Confident"),
    ("bit_confident", "A Bit Confident"),
    ("very_confident", "Very Confident"),
]

SESSION_GOAL_CHOICES = [
    ("pass", "Pass the exam"),
    ("high_score", "Get a high score"),
    ("learn", "Learn and improve"),
    ("finish", "Just finish"),
]


class ReviewSetupForm(forms.Form):
    """Student picks 3+ courses (subjects) + difficulty, then pre-exam wizard."""

    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        label="Courses",
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_MULTISELECT_CLASS,
                "id": "id_setup_subjects",
                "size": "8",
            }
        ),
        help_text=f"Hold Ctrl/Cmd to select at least {MIN_EXAM_SUBJECTS} courses.",
    )
    difficulty = forms.ChoiceField(
        choices=PILOT_DIFFICULTY_CHOICES,
        label="Difficulty",
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_setup_difficulty"}),
    )
    pre_session_confidence = forms.ChoiceField(
        choices=PRE_SESSION_CONFIDENCE_CHOICES,
        required=False,
        widget=forms.HiddenInput(),
    )
    session_goal = forms.ChoiceField(
        choices=SESSION_GOAL_CHOICES,
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        self._exam_target = None
        qs = subjects_available_for_student(student)
        self.fields["subjects"].queryset = qs
        self.fields["subjects"].label_from_instance = (
            lambda obj: f"{obj.code} — {obj.name}"
        )

    def clean(self):
        cleaned = super().clean()
        if not self.student:
            raise forms.ValidationError("Student is required.")

        eligibility = student_setup_eligibility(self.student)
        if not eligibility.get("eligible"):
            raise forms.ValidationError(eligibility["message"])

        subjects = cleaned.get("subjects")
        difficulty = cleaned.get("difficulty")
        if not subjects or not difficulty:
            return cleaned

        if subjects.count() < MIN_EXAM_SUBJECTS:
            raise forms.ValidationError(
                f"Select at least {MIN_EXAM_SUBJECTS} courses before starting."
            )

        try:
            self._exam_target = build_multi_subject_exam_target(
                self.student, subjects, difficulty
            )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def get_auto_target(self) -> dict:
        """Return resolved multi-subject exam target after successful clean()."""
        if self._exam_target is None:
            raise forms.ValidationError(
                "Form must be validated before starting an exam."
            )
        return self._exam_target


class AnswerForm(forms.Form):
    CONFIDENCE_CHOICES = [(i, str(i)) for i in range(1, 6)]

    confidence = forms.ChoiceField(
        choices=CONFIDENCE_CHOICES,
        required=False,
        initial="3",
        widget=forms.HiddenInput(attrs={"id": "confidence-input"}),
    )
    numeric_response = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-lg border-gray-300",
                "placeholder": "Enter your answer",
            }
        ),
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
        if not self.timed_exam and not cleaned.get("confidence"):
            raise forms.ValidationError("Please select your confidence level.")
        if not cleaned.get("selected_choice") and not cleaned.get("numeric_response"):
            if "selected_choice" in self.fields or "numeric_response" in self.fields:
                raise forms.ValidationError("Please select an answer.")
        return cleaned

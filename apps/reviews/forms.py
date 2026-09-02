from django import forms

from apps.questions.models import Question, Subject
from apps.reviews.exam_setup_services import (
    MIN_EXAM_SUBJECTS,
    build_multi_subject_exam_target,
    student_setup_eligibility,
    subjects_available_for_student,
)

FORM_INPUT_CLASS = (
    "w-full border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)

FORM_MULTISELECT_CLASS = (
    "multi-select-native w-full border border-slate-200 px-4 py-2.5 text-examiq-navy "
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
    """Student picks course subjects + difficulty, then pre-exam wizard."""

    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        label="Course subject",
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_MULTISELECT_CLASS,
                "id": "id_setup_subjects",
                "size": "8",
            }
        ),
        help_text=f"Hold Ctrl/Cmd to select at least {MIN_EXAM_SUBJECTS} course subjects.",
    )
    difficulty = forms.ChoiceField(
        choices=PILOT_DIFFICULTY_CHOICES,
        label="Difficulty",
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_setup_difficulty"}),
    )
    question_type = forms.MultipleChoiceField(
        choices=Question.QuestionType.choices,
        initial=[Question.QuestionType.MCQ],
        label="Question types",
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_MULTISELECT_CLASS,
                "id": "id_setup_question_type",
                "size": "5",
            }
        ),
        help_text="Select one or more question types.",
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

    def __init__(self, *args, student=None, preselected_subject=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        self._exam_target = None
        qs = subjects_available_for_student(student)
        self.fields["subjects"].queryset = qs
        self.fields["subjects"].label_from_instance = (
            lambda obj: f"{obj.code} — {obj.name}"
        )
        if preselected_subject is not None and qs.filter(pk=preselected_subject.pk).exists():
            self.fields["subjects"].initial = [preselected_subject.pk]
            self.initial["subjects"] = [preselected_subject.pk]

    def clean(self):
        cleaned = super().clean()
        if not self.student:
            raise forms.ValidationError("Student is required.")

        eligibility = student_setup_eligibility(self.student)
        if not eligibility.get("eligible"):
            raise forms.ValidationError(eligibility["message"])

        subjects = cleaned.get("subjects")
        difficulty = cleaned.get("difficulty")
        question_types = list(cleaned.get("question_type") or [])
        if Question.QuestionType.MCQ not in question_types:
            question_types.insert(0, Question.QuestionType.MCQ)
        cleaned["question_type"] = question_types
        if not subjects or not difficulty:
            return cleaned
        if not question_types:
            self.add_error("question_type", "Select at least one question type.")
            return cleaned

        if subjects.count() < MIN_EXAM_SUBJECTS:
            raise forms.ValidationError(
                f"Select at least {MIN_EXAM_SUBJECTS} course subjects before starting."
            )

        try:
            self._exam_target = build_multi_subject_exam_target(
                self.student, subjects, difficulty, question_types=question_types
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
    TRUE_FALSE_CHOICES = [("True", "True"), ("False", "False")]

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
        self.question = question
        if question:
            if question.question_type == Question.QuestionType.MCQ:
                self.fields["selected_choice"].queryset = question.choices.all()
                del self.fields["numeric_response"]
            elif question.question_type == Question.QuestionType.TRUE_FALSE:
                del self.fields["selected_choice"]
                self.fields["numeric_response"] = forms.ChoiceField(
                    choices=self.TRUE_FALSE_CHOICES,
                    required=False,
                    widget=forms.RadioSelect,
                )
            elif question.question_type == Question.QuestionType.ENUMERATION:
                del self.fields["selected_choice"]
                self.fields["numeric_response"].widget = forms.Textarea(
                    attrs={
                        "class": "w-full rounded-lg border-gray-300",
                        "rows": 4,
                        "placeholder": "Enter one item per line",
                    }
                )
            else:
                # identification / numeric / other free-text
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

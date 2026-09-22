from django import forms

from apps.questions.models import Question, Subject
from apps.reviews.exam_setup_services import (
    MIN_EXAM_SUBJECTS,
    build_multi_subject_exam_target,
    other_subjects_available_for_student,
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
    """Year-level subjects by default; optional extra subjects from other years."""

    year_subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Course subjects for your year",
        widget=forms.CheckboxSelectMultiple(),
        help_text="Uncheck any year-level subjects you want to skip.",
    )
    extra_subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Other course subjects",
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_MULTISELECT_CLASS,
                "id": "id_setup_extra_subjects",
                "size": "8",
            }
        ),
        help_text="Optional. Leave empty to use only your year-level course subjects.",
    )
    difficulty = forms.ChoiceField(
        choices=PILOT_DIFFICULTY_CHOICES,
        label="Difficulty",
        initial=Question.Difficulty.EASY,
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_setup_difficulty"}),
    )
    question_type = forms.MultipleChoiceField(
        choices=Question.AUTHORABLE_QUESTION_TYPE_CHOICES,
        initial=[Question.QuestionType.MCQ],
        label="Question types",
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": FORM_MULTISELECT_CLASS,
                "id": "id_setup_question_type",
                "size": "1",
            }
        ),
        help_text="Exams use Multiple Choice questions.",
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
        self.year_subjects = list(subjects_available_for_student(student))
        self.other_subjects = list(other_subjects_available_for_student(student))
        self.preselected_subject = preselected_subject

        year_qs = subjects_available_for_student(student)
        self.fields["year_subjects"].queryset = year_qs
        self.fields["year_subjects"].label_from_instance = (
            lambda obj: f"{obj.code} — {obj.name}"
        )
        if not self.is_bound:
            self.fields["year_subjects"].initial = list(year_qs.values_list("pk", flat=True))

        other_qs = other_subjects_available_for_student(student)
        self.fields["extra_subjects"].queryset = other_qs
        self.fields["extra_subjects"].label_from_instance = (
            lambda obj: f"{obj.code} — {obj.name} ({obj.year_level.name})"
        )
        if not other_qs.exists():
            self.fields["extra_subjects"].disabled = True

        # Student Start Exam is Multiple Choice only.
        self.fields["question_type"].choices = list(
            Question.AUTHORABLE_QUESTION_TYPE_CHOICES
        )

    def clean(self):
        cleaned = super().clean()
        if not self.student:
            raise forms.ValidationError("Student is required.")

        eligibility = student_setup_eligibility(self.student)
        if not eligibility.get("eligible"):
            raise forms.ValidationError(eligibility["message"])

        difficulty = cleaned.get("difficulty")
        cleaned["question_type"] = [Question.QuestionType.MCQ]
        question_types = cleaned["question_type"]
        if not difficulty:
            return cleaned
        if not question_types:
            self.add_error("question_type", "Select at least one question type.")
            return cleaned

        from apps.questions.services import count_available_questions_for_subject

        # Posted year-level selection + optional extras (no longer force all year subjects).
        selected = list(cleaned.get("year_subjects") or [])
        extra = list(cleaned.get("extra_subjects") or [])
        seen_ids = {s.pk for s in selected}
        for subject in extra:
            if subject.pk not in seen_ids:
                selected.append(subject)
                seen_ids.add(subject.pk)

        if not selected:
            raise forms.ValidationError(
                "Select at least one course subject to start an exam."
            )

        subjects = [
            subject
            for subject in selected
            if count_available_questions_for_subject(
                subject, difficulty, question_types=question_types
            )
            >= 1
        ]
        cleaned["subjects"] = subjects

        if len(subjects) < MIN_EXAM_SUBJECTS:
            raise forms.ValidationError(
                "No approved questions are available for the selected course "
                "subjects at this difficulty and question type."
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
    # Guessing / Not sure / Sure map onto the stored 1 / 3 / 5 scale.
    CONFIDENCE_CHOICES = [
        (1, "Guessing"),
        (3, "Not sure"),
        (5, "Sure"),
    ]
    TRUE_FALSE_CHOICES = [("True", "True"), ("False", "False")]

    confidence = forms.ChoiceField(
        choices=CONFIDENCE_CHOICES,
        required=False,
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
        if not cleaned.get("confidence"):
            raise forms.ValidationError("Please select how sure you were.")
        if cleaned.get("timed_out"):
            return cleaned
        if not cleaned.get("selected_choice") and not cleaned.get("numeric_response"):
            if "selected_choice" in self.fields or "numeric_response" in self.fields:
                raise forms.ValidationError("Please select an answer.")
        return cleaned

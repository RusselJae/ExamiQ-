from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.questions.models import ExplanationStep, Question, QuestionChoice, Subject, Topic

INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)

CHOICE_LABELS = ("A", "B", "C", "D")


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            "topic",
            "difficulty",
            "question_type",
            "stem",
            "concept_tag",
            "correct_answer",
            "tolerance",
            "is_active",
        ]
        widgets = {
            "topic": forms.Select(attrs={"class": INPUT_CLASS}),
            "difficulty": forms.Select(attrs={"class": INPUT_CLASS}),
            "question_type": forms.Select(attrs={"class": INPUT_CLASS}),
            "stem": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 4}),
            "correct_answer": forms.NumberInput(attrs={"class": INPUT_CLASS}),
            "tolerance": forms.NumberInput(attrs={"class": INPUT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
        }

    def __init__(self, *args, program=None, **kwargs):
        super().__init__(*args, **kwargs)
        if program:
            self.fields["topic"].queryset = Topic.objects.filter(subject__program=program)
        self.fields["correct_answer"].required = False
        self.fields["tolerance"].required = False

    def clean(self):
        cleaned = super().clean()
        question_type = cleaned.get("question_type")
        correct_answer = cleaned.get("correct_answer")
        if question_type == Question.QuestionType.NUMERIC and correct_answer is None:
            raise forms.ValidationError("Numeric questions require a correct answer.")
        if question_type == Question.QuestionType.MCQ:
            cleaned["correct_answer"] = None
        return cleaned


class QuestionEditForm(forms.ModelForm):
    """Professor question form with Multiple Choice default and text-answer types."""

    class Meta:
        model = Question
        fields = [
            "topic",
            "difficulty",
            "question_type",
            "stem",
            "concept_tag",
            "expected_answer",
            "is_active",
        ]
        widgets = {
            "topic": forms.Select(attrs={"class": INPUT_CLASS}),
            "difficulty": forms.Select(attrs={"class": INPUT_CLASS}),
            "question_type": forms.Select(attrs={"class": INPUT_CLASS, "id": "id_question_type"}),
            "stem": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 4,
                    "placeholder": "Question text. Supports LaTeX with $...$ delimiters.",
                }
            ),
            "concept_tag": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Short concept label"}
            ),
            "expected_answer": forms.Textarea(
                attrs={
                    "class": INPUT_CLASS,
                    "rows": 3,
                    "id": "id_expected_answer",
                    "placeholder": "Expected answer (one item per line for Enumeration)",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
        }

    def __init__(self, *args, program=None, **kwargs):
        super().__init__(*args, **kwargs)
        if program:
            self.fields["topic"].queryset = Topic.objects.filter(
                subject__program=program
            )
        # Faculty authoring is Multiple Choice only (other types remain for legacy rows).
        self.fields["question_type"].choices = list(
            Question.AUTHORABLE_QUESTION_TYPE_CHOICES
        )
        self.fields["question_type"].widget = forms.HiddenInput(
            attrs={"id": "id_question_type"}
        )
        self.fields["question_type"].initial = Question.QuestionType.MCQ
        self.fields["expected_answer"].required = False

    def clean(self):
        cleaned = super().clean()
        # New and edited faculty questions are forced to Multiple Choice.
        cleaned["question_type"] = Question.QuestionType.MCQ
        cleaned["expected_answer"] = ""
        return cleaned


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Topic name"}
            ),
        }


class SimplifiedQuestionChoiceForm(forms.ModelForm):
    class Meta:
        model = QuestionChoice
        fields = ["text", "is_correct", "error_type"]
        widgets = {
            "text": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "is_correct": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 correct-choice-cb"}),
            "error_type": forms.Select(attrs={"class": INPUT_CLASS}),
        }


class BaseSimplifiedChoiceFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        texts = [
            form.cleaned_data.get("text", "").strip()
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if sum(1 for t in texts if t) < 2:
            raise forms.ValidationError("Provide at least two answer choices.")
        if not any(
            form.cleaned_data.get("is_correct")
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ):
            raise forms.ValidationError("Mark one choice as correct.")

    def save(self, commit=True):
        instances = super().save(commit=False)
        for index, instance in enumerate(instances):
            if index < len(CHOICE_LABELS):
                instance.label = CHOICE_LABELS[index]
            if commit:
                instance.save()
        if commit:
            self.save_m2m()
        return instances


SimplifiedQuestionChoiceFormSet = inlineformset_factory(
    Question,
    QuestionChoice,
    form=SimplifiedQuestionChoiceForm,
    formset=BaseSimplifiedChoiceFormSet,
    fields=["text", "is_correct", "error_type"],
    extra=4,
    max_num=4,
    can_delete=False,
)

QuestionChoiceFormSet = inlineformset_factory(
    Question,
    QuestionChoice,
    fields=["label", "text", "is_correct", "error_type"],
    extra=4,
    max_num=4,
    can_delete=True,
    widgets={
        "label": forms.TextInput(attrs={"class": INPUT_CLASS}),
        "text": forms.TextInput(attrs={"class": INPUT_CLASS}),
        "is_correct": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
        "error_type": forms.Select(attrs={"class": INPUT_CLASS}),
    },
)

ExplanationStepFormSet = inlineformset_factory(
    Question,
    ExplanationStep,
    fields=["order", "content", "professor_note"],
    extra=2,
    can_delete=True,
    widgets={
        "order": forms.NumberInput(attrs={"class": INPUT_CLASS}),
        "content": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
        "professor_note": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
    },
)

from django import forms

from apps.questions.curriculum import subject_queryset_for_student
from apps.questions.models import Question, Subject, Topic
from apps.questions.services import count_available_questions
from apps.reviews.exam_setup_services import (
    assignment_for_student_subject,
    difficulties_for_student_subject,
    student_setup_eligibility,
    topics_for_student_subject,
)
from apps.users.models import User

FORM_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
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
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(),
        label="Subject",
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_subject"}),
    )
    topic = forms.ModelChoiceField(
        queryset=Topic.objects.none(),
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_topic"}),
    )
    difficulty = forms.ChoiceField(
        choices=PILOT_DIFFICULTY_CHOICES,
        widget=forms.Select(attrs={"class": FORM_INPUT_CLASS, "id": "id_difficulty"}),
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
        if student:
            self.fields["subject"].queryset = subject_queryset_for_student(student)

        subject = None
        if self.data.get("subject"):
            try:
                subject = Subject.objects.get(pk=self.data["subject"])
            except (Subject.DoesNotExist, ValueError, KeyError):
                pass
        elif self.initial.get("subject"):
            subject = self.initial["subject"]
        if subject and student:
            self.fields["topic"].queryset = topics_for_student_subject(student, subject)
            allowed = difficulties_for_student_subject(student, subject)
            if allowed:
                self.fields["difficulty"].choices = [
                    c for c in PILOT_DIFFICULTY_CHOICES if c[0] in allowed
                ]
            topic_initial = self.initial.get("topic")
            if topic_initial and not self.data.get("topic"):
                self.fields["topic"].initial = topic_initial

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get("subject")
        topic = cleaned.get("topic")
        difficulty = cleaned.get("difficulty")

        if self.student:
            eligibility = student_setup_eligibility(self.student)
            if not eligibility.get("eligible"):
                raise forms.ValidationError(eligibility["message"])

        if subject and topic and topic.subject_id != subject.pk:
            raise forms.ValidationError("Selected topic does not belong to this subject.")

        if self.student and subject:
            allowed_topics = topics_for_student_subject(self.student, subject)
            if topic and not allowed_topics.filter(pk=topic.pk).exists():
                raise forms.ValidationError("Selected topic is not available for this exam.")
            allowed_difficulties = difficulties_for_student_subject(self.student, subject)
            if difficulty and allowed_difficulties and difficulty not in allowed_difficulties:
                raise forms.ValidationError(
                    "Selected difficulty is not available for this exam."
                )

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
        if subject and self.student:
            assignment = assignment_for_student_subject(self.student, subject)
            if assignment:
                return assignment.course
        return None


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
        if not self.timed_exam and not cleaned.get("confidence"):
            raise forms.ValidationError("Please select your confidence level.")
        if not cleaned.get("selected_choice") and not cleaned.get("numeric_response"):
            if "selected_choice" in self.fields or "numeric_response" in self.fields:
                raise forms.ValidationError("Please select an answer.")
        return cleaned

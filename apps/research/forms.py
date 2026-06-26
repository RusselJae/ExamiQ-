from django import forms

from apps.research.models import PilotConsent, SurveyResponse

LIKERT_CHOICES = [(i, str(i)) for i in range(1, 6)]

FORM_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)


class PilotConsentForm(forms.ModelForm):
    class Meta:
        model = PilotConsent
        fields = ["consented"]
        widgets = {
            "consented": forms.CheckboxInput(
                attrs={"class": "rounded border-slate-300 text-examiq-green focus:ring-green-100"}
            ),
        }


class PreSurveyForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = [
            "calibration_awareness",
            "confidence_rating_usefulness",
            "would_recommend",
            "open_feedback",
        ]
        widgets = {
            "calibration_awareness": forms.Select(attrs={"class": FORM_INPUT_CLASS}),
            "confidence_rating_usefulness": forms.Select(attrs={"class": FORM_INPUT_CLASS}),
            "would_recommend": forms.Select(attrs={"class": FORM_INPUT_CLASS}),
            "open_feedback": forms.Textarea(
                attrs={"class": FORM_INPUT_CLASS, "rows": 3, "placeholder": "Optional comments"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("calibration_awareness", "confidence_rating_usefulness", "would_recommend"):
            self.fields[field].choices = LIKERT_CHOICES
            self.fields[field].label = {
                "calibration_awareness": "I am aware of how confidence affects learning",
                "confidence_rating_usefulness": "Rating confidence after each answer is useful",
                "would_recommend": "I would recommend EXAMIQ to classmates",
            }[field]


class PostSurveyForm(PreSurveyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["calibration_awareness"].label = (
            "EXAMIQ helped me understand my calibration gaps"
        )
        self.fields["confidence_rating_usefulness"].label = (
            "Confidence ratings improved my self-regulated learning"
        )
        self.fields["would_recommend"].label = (
            "I would recommend EXAMIQ after using it"
        )

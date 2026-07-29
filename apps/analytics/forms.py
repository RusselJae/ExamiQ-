from django import forms

from apps.analytics.models import MistakeRecord

NOTE_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _clean_concern_image(image):
    if not image:
        return image
    if getattr(image, "size", 0) > MAX_IMAGE_BYTES:
        raise forms.ValidationError("Image must be 5 MB or smaller.")
    content_type = getattr(image, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise forms.ValidationError("Use a JPEG, PNG, or WebP image.")
    name = (getattr(image, "name", "") or "").lower()
    if name and not name.endswith((".jpg", ".jpeg", ".png", ".webp")):
        raise forms.ValidationError("Use a JPEG, PNG, or WebP image.")
    return image


class MistakeConcernForm(forms.Form):
    """Compose a new message in a concern thread."""

    body = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": NOTE_CLASS,
                "rows": 3,
                "placeholder": "Describe what confused you or ask about this mistake…",
            }
        ),
    )
    image = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "class": "w-full text-sm text-examiq-slate",
                "accept": "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp",
            }
        ),
    )

    def clean_image(self):
        return _clean_concern_image(self.cleaned_data.get("image"))

    def clean(self):
        cleaned = super().clean()
        body = (cleaned.get("body") or "").strip()
        image = cleaned.get("image")
        if not body and not image:
            raise forms.ValidationError("Add a message or photo.")
        cleaned["body"] = body
        return cleaned


class MistakeConcernLegacyForm(forms.ModelForm):
    """Legacy form kept for tests referencing MistakeRecord fields."""

    class Meta:
        model = MistakeRecord
        fields = ["student_note", "student_image"]
        widgets = {
            "student_note": forms.Textarea(
                attrs={
                    "class": NOTE_CLASS,
                    "rows": 3,
                    "placeholder": "Describe what confused you or ask about this mistake…",
                }
            ),
            "student_image": forms.ClearableFileInput(
                attrs={
                    "class": "w-full text-sm text-examiq-slate",
                    "accept": "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp",
                }
            ),
        }

    def clean_student_image(self):
        return _clean_concern_image(self.cleaned_data.get("student_image"))

"""Custom forms for EXAMIQ auth and shared input styling."""

from django import forms
from django.utils import timezone
from allauth.account.adapter import get_adapter
from allauth.account.forms import ChangePasswordForm, LoginForm, SignupForm
from allauth.account.utils import filter_users_by_email

from apps.questions.models import YearLevel
from apps.users.models import Course, Program, User, Department

INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)


def _style_fields(form: forms.Form) -> None:
    for field in form.fields.values():
        if hasattr(field.widget, "attrs"):
            field.widget.attrs.setdefault("class", INPUT_CLASS)


class ExamiQLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class ExamiQSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["password2"].label = "Confirm password"
        self.fields["password1"].help_text = ""

    def save(self, request):
        user = super().save(request)
        user.role = User.Role.STUDENT
        user.save(update_fields=["role"])
        return user


MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_PROFILE_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ProfileUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False, label="First name")
    middle_name = forms.CharField(max_length=150, required=False, label="Middle name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    profile_photo = forms.ImageField(required=False, label="Profile photo")
    home_degree_program = forms.ChoiceField(
        choices=[("", "— Select your program —")] + list(User.HomeDegreeProgram.choices),
        required=False,
        label="Home degree program",
    )
    year_level = forms.ModelChoiceField(
        queryset=YearLevel.objects.all(),
        required=False,
        empty_label="— Select year level —",
        label="Year level",
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = user.first_name
        self.fields["middle_name"].initial = user.middle_name
        self.fields["last_name"].initial = user.last_name
        if user.role != User.Role.STUDENT:
            del self.fields["home_degree_program"]
            del self.fields["year_level"]
        else:
            self.fields["home_degree_program"].initial = user.home_degree_program
            self.fields["year_level"].initial = user.year_level
        _style_fields(self)
        self.fields["profile_photo"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        if photo.size > MAX_PROFILE_PHOTO_BYTES:
            raise forms.ValidationError("Photo must be 2 MB or smaller.")
        content_type = getattr(photo, "content_type", "")
        if content_type and content_type not in ALLOWED_PROFILE_PHOTO_TYPES:
            raise forms.ValidationError("Upload a JPEG, PNG, or WebP image.")
        return photo

    def save(self) -> None:
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.middle_name = self.cleaned_data.get("middle_name", "")
        self.user.last_name = self.cleaned_data["last_name"]
        update_fields = ["first_name", "middle_name", "last_name"]
        photo = self.cleaned_data.get("profile_photo")
        if photo:
            if self.user.profile_photo:
                self.user.profile_photo.delete(save=False)
            self.user.profile_photo = photo
            update_fields.append("profile_photo")
        if self.user.role == User.Role.STUDENT and "home_degree_program" in self.cleaned_data:
            self.user.home_degree_program = self.cleaned_data["home_degree_program"] or ""
            update_fields.append("home_degree_program")
        if self.user.role == User.Role.STUDENT and "year_level" in self.cleaned_data:
            self.user.year_level = self.cleaned_data["year_level"]
            update_fields.append("year_level")
        self.user.save(update_fields=update_fields)


class CampusUserCreateForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(
        label="Temporary password",
        widget=forms.PasswordInput,
        min_length=8,
    )
    first_name = forms.CharField(max_length=150, required=False, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by("name"),
        required=False,
        empty_label="— No department —",
        label="Department",
    )

    def __init__(self, *args, role: str, department_required: bool = False, **kwargs):
        self.role = role
        self.department_required = department_required
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["department"].required = department_required
        if department_required:
            self.fields["department"].empty_label = "— Select department —"

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def save(self) -> User:
        department = self.cleaned_data.get("department")
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            role=self.role,
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
            department=department,
        )


class CampusProfessorCreateForm(CampusUserCreateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, role=User.Role.PROFESSOR, department_required=False, **kwargs)


class CampusChairpersonCreateForm(CampusUserCreateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, role=User.Role.CHAIRPERSON, department_required=True, **kwargs)


class CourseOfferingForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "name", "program", "term", "academic_year", "section"]
        widgets = {
            "code": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "MATH101"}),
            "name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "College Algebra"}),
            "program": forms.Select(attrs={"class": INPUT_CLASS}),
            "term": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "1st Sem"}),
            "academic_year": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "2026"}),
            "section": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "A"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["program"].queryset = Program.objects.all().order_by("name")


class EmailChangeRequestForm(forms.Form):
    email = forms.EmailField(required=True, label="New email")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_email(self) -> str:
        value = self.cleaned_data["email"].lower()
        adapter = get_adapter()
        value = adapter.clean_email(value)

        if value == self.user.email.lower():
            raise forms.ValidationError("This is already your login email.")

        users = filter_users_by_email(value)
        on_diff_account = [user for user in users if user.pk != self.user.pk]
        if on_diff_account:
            raise adapter.validation_error("email_taken")

        return value

    def save(self, request) -> str:
        from apps.users.services import request_email_change

        return request_email_change(request, self.user, self.cleaned_data["email"])


class ExamiQChangePasswordForm(ChangePasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["password1"].help_text = ""
        self.fields["password2"].label = "Confirm new password"

    def save(self) -> None:
        super().save()
        self.user.password_changed_at = timezone.now()
        self.user.save(update_fields=["password_changed_at"])

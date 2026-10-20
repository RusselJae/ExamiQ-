"""Custom forms for EXAMIQ auth and shared input styling."""

import re

from allauth.account.adapter import get_adapter
from allauth.account.forms import (
    ChangePasswordForm,
    LoginForm,
    ResetPasswordForm,
    ResetPasswordKeyForm,
    SignupForm,
)
from allauth.account.utils import filter_users_by_email
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.questions.models import Subject, YearLevel
from apps.users.models import (
    AcademicTerm,
    AcademicYear,
    Course,
    Department,
    Program,
    ProgramSection,
    User,
)
from apps.users.section_services import (
    get_current_academic_year,
    get_or_create_student_section,
    parse_section_label,
    section_matches_student,
    sections_for_student,
    validate_section_capacity,
)

INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-examiq-navy "
    "focus:border-examiq-green focus:ring-2 focus:ring-green-100 outline-none transition"
)

AUTH_SELECT_CLASS = "auth-field__input"

STUDENT_NUMBER_RE = re.compile(r"^\d{9}$")
PHONE_NUMBER_RE = re.compile(r"^\d{11}$")
EDUCATION_DEPARTMENT_NAME = "College of Education"


def _style_fields(form: forms.Form) -> None:
    for field in form.fields.values():
        if hasattr(field.widget, "attrs"):
            field.widget.attrs.setdefault("class", INPUT_CLASS)


def _style_auth_fields(form: forms.Form) -> None:
    """Apply auth-screen input classes (matches auth_field.html)."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", AUTH_SELECT_CLASS)
        elif hasattr(widget, "attrs"):
            widget.attrs.setdefault("class", "auth-field__input")


def _clean_digits(value: str, label: str, length: int) -> str:
    if not value:
        raise forms.ValidationError(f"{label} is required.")
    if not re.fullmatch(rf"\d{{{length}}}", value):
        raise forms.ValidationError(f"{label} must be exactly {length} digits.")
    return value


class ExamiQLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_auth_fields(self)
        if "login" in self.fields:
            self.fields["login"].label = "Email"
            self.fields["login"].widget.attrs["placeholder"] = "name@school.edu.ph"
        if "password" in self.fields:
            self.fields["password"].widget.attrs.setdefault(
                "placeholder", "Your password"
            )


class ExamiQResetPasswordForm(ResetPasswordForm):
    """Forgot-password form with existence check and request throttling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle_error = None
        _style_auth_fields(self)
        email = self.fields.get("email")
        if email:
            email.label = "Email"
            email.widget.attrs.setdefault("placeholder", "name@school.edu.ph")
            email.widget.attrs.setdefault("autocomplete", "email")

    def clean_email(self):
        from allauth.account.utils import filter_users_by_email

        from apps.users.password_reset_services import (
            PasswordResetThrottleError,
            check_password_reset_allowed,
            email_has_account,
            normalize_reset_email,
        )

        email = normalize_reset_email(self.cleaned_data.get("email", ""))
        if not email:
            raise forms.ValidationError("Enter your email address.")
        if not email_has_account(email):
            raise forms.ValidationError(
                "No account is registered with this email address."
            )
        try:
            check_password_reset_allowed(email)
        except PasswordResetThrottleError as exc:
            self.throttle_error = exc
            raise forms.ValidationError(str(exc)) from exc
        # allauth save() expects self.users from the parent clean_email path.
        self.users = filter_users_by_email(email, is_active=True, prefer_verified=True)
        if not self.users:
            # Include inactive approved accounts that can still reset.
            self.users = list(User.objects.filter(email__iexact=email))
        return email

    def save(self, request, **kwargs):
        from apps.users.password_reset_services import (
            normalize_reset_email,
            record_password_reset_request,
        )

        email = normalize_reset_email(self.cleaned_data["email"])
        ip = (request.META.get("REMOTE_ADDR") or "")[:45] or None
        record_password_reset_request(email, ip_address=ip)
        if not getattr(self, "users", None):
            self.users = list(User.objects.filter(email__iexact=email))
        return super().save(request, **kwargs)


class ExamiQResetPasswordKeyForm(ResetPasswordKeyForm):
    """Branded widgets for setting a new password from a reset link."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_auth_fields(self)
        if "password1" in self.fields:
            self.fields["password1"].label = "New password"
            self.fields["password1"].widget.attrs.setdefault(
                "autocomplete", "new-password"
            )
        if "password2" in self.fields:
            self.fields["password2"].label = "Confirm new password"
            self.fields["password2"].widget.attrs.setdefault(
                "autocomplete", "new-password"
            )


class ExamiQSignupForm(SignupForm):
    SIGNUP_ROLE_CHOICES = [
        (User.Role.STUDENT, "Student"),
    ]

    role = forms.ChoiceField(
        choices=SIGNUP_ROLE_CHOICES,
        initial=User.Role.STUDENT,
        widget=forms.HiddenInput(),
    )
    first_name = forms.CharField(
        max_length=100,
        label="First name",
        widget=forms.TextInput(
            attrs={
                "class": "auth-field__input",
                "placeholder": "First name",
                "autocomplete": "given-name",
                "maxlength": "100",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=100,
        label="Last name",
        widget=forms.TextInput(
            attrs={
                "class": "auth-field__input",
                "placeholder": "Last name",
                "autocomplete": "family-name",
                "maxlength": "100",
            }
        ),
    )
    middle_name = forms.CharField(
        max_length=100,
        required=False,
        label="Middle name (optional)",
        widget=forms.TextInput(
            attrs={
                "class": "auth-field__input",
                "placeholder": "Middle name",
                "autocomplete": "additional-name",
                "maxlength": "100",
            }
        ),
    )
    suffix = forms.CharField(
        max_length=20,
        required=False,
        label="Suffix (optional)",
        widget=forms.TextInput(
            attrs={
                "class": "auth-field__input",
                "placeholder": "Jr., Sr., III",
                "autocomplete": "honorific-suffix",
            }
        ),
    )
    student_number = forms.CharField(
        max_length=9,
        required=False,
        label="Student number",
        widget=forms.TextInput(
            attrs={
                "class": "auth-field__input",
                "inputmode": "numeric",
                "pattern": r"\d{9}",
                "maxlength": "9",
                "placeholder": "9-digit student ID",
            }
        ),
    )
    employee_id = forms.CharField(
        max_length=50,
        required=False,
        label="Employee ID",
        widget=forms.TextInput(
            attrs={
                "class": "auth-field__input",
                "placeholder": "Employee ID",
            }
        ),
    )
    phone_number = forms.CharField(
        max_length=11,
        required=False,
        label="Phone number",
        widget=forms.HiddenInput(),
    )
    year_level = forms.ModelChoiceField(
        queryset=YearLevel.objects.none(),
        required=False,
        empty_label="— Select year level —",
        label="Year level",
        widget=forms.Select(attrs={"class": AUTH_SELECT_CLASS, "id": "id_year_level"}),
    )
    section = forms.ModelChoiceField(
        queryset=ProgramSection.objects.none(),
        required=False,
        empty_label="— Select section —",
        label="Section",
        widget=forms.Select(
            attrs={
                "class": AUTH_SELECT_CLASS,
                "id": "id_section",
                "data-program": User.HomeDegreeProgram.BSED_MATH,
            }
        ),
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_auth_fields(self)
        for name in ("email", "password1", "password2"):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "auth-field__input")
        if "email" in self.fields:
            self.fields["email"].widget.attrs["placeholder"] = "name@school.edu.ph"
        if "password1" in self.fields:
            self.fields["password1"].label = "Password"
            self.fields["password1"].help_text = ""
            self.fields["password1"].widget.attrs["placeholder"] = "Create a password"
        if "password2" in self.fields:
            self.fields["password2"].label = "Confirm password"
            self.fields["password2"].widget.attrs.setdefault(
                "placeholder", "Re-enter password"
            )

        self.fields["year_level"].queryset = YearLevel.objects.order_by("order")
        year_level_id = None
        if self.data.get("year_level"):
            try:
                year_level_id = int(self.data.get("year_level"))
            except (TypeError, ValueError):
                year_level_id = None
        self.fields["section"].queryset = sections_for_student(
            User.HomeDegreeProgram.BSED_MATH,
            year_level_id,
        )
        self.fields["section"].label_from_instance = lambda obj: obj.display_label
        self.fields["section"].widget.attrs["data-program"] = (
            User.HomeDegreeProgram.BSED_MATH
        )
        self.fields["section"].widget.attrs["data-sections-url"] = (
            "/profile/api/sections/"
        )
    def clean_first_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("first_name", ""),
            field_label="First name",
            required=True,
        )

    def clean_last_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("last_name", ""),
            field_label="Last name",
            required=True,
        )

    def clean_middle_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("middle_name", ""),
            field_label="Middle name",
            required=False,
        )

    def clean_student_number(self):
        value = self.cleaned_data.get("student_number", "").strip()
        role = self.data.get("role", User.Role.STUDENT)
        if role != User.Role.STUDENT:
            return ""
        return _clean_digits(value, "Student number", 9)

    def clean_phone_number(self):
        value = self.cleaned_data.get("phone_number", "").strip()
        digits = re.sub(r"\D", "", value)
        if len(digits) == 10 and digits.startswith("9"):
            digits = "0" + digits
        if len(digits) == 11 and digits.startswith("09"):
            return digits
        if not digits:
            raise forms.ValidationError("Phone number is required.")
        raise forms.ValidationError(
            "Enter a valid 10-digit mobile number (9XX XXX XXXX)."
        )

    def clean_employee_id(self):
        value = self.cleaned_data.get("employee_id", "").strip()
        role = self.data.get("role", User.Role.STUDENT)
        if role == User.Role.PROFESSOR and not value:
            raise forms.ValidationError("Employee ID is required.")
        return value

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role", User.Role.STUDENT)
        if role == User.Role.STUDENT:
            student_number = cleaned.get("student_number")
            if (
                student_number
                and User.objects.filter(student_number=student_number).exists()
            ):
                self.add_error(
                    "student_number", "This student number is already registered."
                )
        year_level = cleaned.get("year_level")
        section = cleaned.get("section")
        if role == User.Role.STUDENT:
            if not year_level:
                self.add_error("year_level", "Year level is required.")
            if not section:
                self.add_error("section", "Section is required.")
            elif year_level and "section" not in self.errors:
                if not section_matches_student(
                    section,
                    User.HomeDegreeProgram.BSED_MATH,
                    year_level.pk,
                ):
                    self.add_error(
                        "section", "Choose a section for the selected year level."
                    )
                else:
                    try:
                        validate_section_capacity(section)
                    except ValidationError as exc:
                        self.add_error(
                            "section",
                            exc.messages[0] if exc.messages else str(exc),
                        )
        return cleaned

    def save(self, request):
        user = super().save(request)
        role = self.cleaned_data["role"]
        user.role = role
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.middle_name = self.cleaned_data.get("middle_name", "").strip()
        user.suffix = self.cleaned_data.get("suffix", "").strip()
        user.phone_number = self.cleaned_data["phone_number"]
        user.student_number = self.cleaned_data["student_number"]
        user.home_degree_program = User.HomeDegreeProgram.BSED_MATH
        user.employee_id = ""
        user.year_level = self.cleaned_data["year_level"]
        user.section = self.cleaned_data["section"]
        # Students sign up freely: the account is approved and only needs the
        # email OTP before it can be used. No faculty activation step.
        user.approval_status = User.ApprovalStatus.APPROVED
        user.is_active = False

        user.save()

        from django.contrib import messages

        from apps.users.otp_services import SIGNUP_OTP_SESSION_KEY, send_signup_otp

        request.session[SIGNUP_OTP_SESSION_KEY] = user.pk
        try:
            send_signup_otp(user, force=True)
        except Exception:
            messages.warning(
                request,
                "Account created, but we could not send the verification email. "
                "Use Resend on the next screen after checking email settings.",
            )
        return user


class FacultySignupForm(ExamiQSignupForm):
    """Public faculty registration request awaiting coordinator approval."""

    role = forms.ChoiceField(
        choices=[(User.Role.PROFESSOR, "Faculty")],
        initial=User.Role.PROFESSOR,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("student_number", "year_level", "section"):
            self.fields.pop(field_name, None)
        self.fields["employee_id"].required = True
        self.fields["employee_id"].help_text = ""

    def clean(self):
        cleaned = super(ExamiQSignupForm, self).clean()
        return cleaned

    def save(self, request):
        user = SignupForm.save(self, request)
        education_department, _ = Department.objects.get_or_create(
            name=EDUCATION_DEPARTMENT_NAME
        )
        user.role = User.Role.PROFESSOR
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.middle_name = self.cleaned_data.get("middle_name", "").strip()
        user.suffix = self.cleaned_data.get("suffix", "").strip()
        user.phone_number = self.cleaned_data["phone_number"]
        user.department = education_department
        user.employee_id = self.cleaned_data["employee_id"]
        user.student_number = None
        user.home_degree_program = ""
        user.year_level = None
        user.section = None
        user.approval_status = User.ApprovalStatus.PENDING
        user.is_active = False
        user.save()

        from django.contrib import messages

        from apps.users.otp_services import SIGNUP_OTP_SESSION_KEY, send_signup_otp

        request.session[SIGNUP_OTP_SESSION_KEY] = user.pk
        try:
            send_signup_otp(user, force=True)
        except Exception:
            messages.warning(
                request,
                "Account request created, but we could not send the verification email. "
                "Use Resend on the next screen after checking email settings.",
            )
        return user


class CoordinatorSignupForm(ExamiQSignupForm):
    """Unlisted program-coordinator registration (secret link only)."""

    role = forms.ChoiceField(
        choices=[(User.Role.PROGRAM_COORDINATOR, "Program Coordinator")],
        initial=User.Role.PROGRAM_COORDINATOR,
        widget=forms.HiddenInput(),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by("name"),
        empty_label="— Select department —",
        label="Department",
        widget=forms.Select(attrs={"class": AUTH_SELECT_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("student_number", "year_level", "section"):
            self.fields.pop(field_name, None)
        self.fields["employee_id"].required = True
        self.fields["employee_id"].help_text = ""
        self.fields["department"].required = True

    def clean(self):
        return super(ExamiQSignupForm, self).clean()

    def save(self, request):
        user = SignupForm.save(self, request)
        user.role = User.Role.PROGRAM_COORDINATOR
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.middle_name = self.cleaned_data.get("middle_name", "").strip()
        user.suffix = self.cleaned_data.get("suffix", "").strip()
        user.phone_number = self.cleaned_data["phone_number"]
        user.department = self.cleaned_data["department"]
        user.employee_id = self.cleaned_data["employee_id"]
        user.student_number = None
        user.home_degree_program = ""
        user.year_level = None
        user.section = None
        user.approval_status = User.ApprovalStatus.PENDING
        user.is_active = False
        user.save()

        from django.contrib import messages

        from apps.users.otp_services import SIGNUP_OTP_SESSION_KEY, send_signup_otp

        request.session[SIGNUP_OTP_SESSION_KEY] = user.pk
        try:
            send_signup_otp(user, force=True)
        except Exception:
            messages.warning(
                request,
                "Account request created, but we could not send the verification email. "
                "Use Resend on the next screen after checking email settings.",
            )
        return user


MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_PROFILE_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ProfileUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=100, required=False, label="First name")
    middle_name = forms.CharField(max_length=100, required=False, label="Middle name")
    last_name = forms.CharField(max_length=100, required=False, label="Last name")
    suffix = forms.CharField(max_length=20, required=False, label="Suffix")
    profile_photo = forms.ImageField(required=False, label="Profile photo")
    year_level = forms.ModelChoiceField(
        queryset=YearLevel.objects.all(),
        required=False,
        empty_label="— Select year level —",
        label="Year level",
    )
    section = forms.CharField(
        required=False,
        max_length=20,
        label="Section",
        widget=forms.TextInput(attrs={"placeholder": "1M or BSE 2-1M"}),
        help_text="Your cohort section for Chat and exam access (e.g. 1M, 2-1M).",
    )
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = user.first_name
        self.fields["middle_name"].initial = user.middle_name
        self.fields["last_name"].initial = user.last_name
        self.fields["suffix"].initial = user.suffix
        _style_fields(self)
        self.fields["profile_photo"].widget.attrs["accept"] = (
            "image/jpeg,image/png,image/webp"
        )

        if user.role == User.Role.STUDENT:
            self.fields["year_level"].queryset = YearLevel.objects.order_by("order")
            self.fields["year_level"].initial = user.year_level
            if user.section_id:
                self.fields["section"].initial = user.section.display_label
        else:
            del self.fields["year_level"]
            del self.fields["section"]

    def clean_first_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("first_name", ""),
            field_label="First name",
            required=False,
        )

    def clean_middle_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("middle_name", ""),
            field_label="Middle name",
            required=False,
        )

    def clean_last_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("last_name", ""),
            field_label="Last name",
            required=False,
        )

    def clean_section(self):
        if self.user.role != User.Role.STUDENT:
            return ""
        value = (self.cleaned_data.get("section") or "").strip()
        if not value:
            raise forms.ValidationError("Section is required.")
        try:
            return parse_section_label(value)
        except ValidationError as exc:
            raise forms.ValidationError(
                exc.messages[0] if exc.messages else str(exc)
            ) from exc

    def clean(self):
        cleaned = super().clean()
        if self.user.role != User.Role.STUDENT:
            return cleaned
        year_level = cleaned.get("year_level")
        section_label = cleaned.get("section")
        if not year_level:
            self.add_error("year_level", "Year level is required.")
        elif section_label and "section" not in self.errors:
            try:
                cleaned["section_obj"] = get_or_create_student_section(
                    year_level,
                    section_label,
                    exclude_user=self.user,
                )
            except ValidationError as exc:
                self.add_error(
                    "section",
                    exc.messages[0] if exc.messages else str(exc),
                )
        return cleaned

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
        self.user.suffix = self.cleaned_data.get("suffix", "").strip()
        update_fields = ["first_name", "middle_name", "last_name", "suffix"]
        photo = self.cleaned_data.get("profile_photo")
        if photo:
            if self.user.profile_photo:
                self.user.profile_photo.delete(save=False)
            self.user.profile_photo = photo
            update_fields.append("profile_photo")
        if self.user.role == User.Role.STUDENT:
            self.user.home_degree_program = User.HomeDegreeProgram.BSED_MATH
            self.user.year_level = self.cleaned_data.get("year_level")
            self.user.section = self.cleaned_data.get("section_obj")
            update_fields.extend(["home_degree_program", "year_level", "section"])
        self.user.save(update_fields=update_fields)


class CampusUserCreateForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(
        label="Temporary password",
        widget=forms.PasswordInput,
        min_length=8,
    )
    first_name = forms.CharField(max_length=100, required=False, label="First name")
    last_name = forms.CharField(max_length=100, required=False, label="Last name")
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by("name"),
        required=False,
        empty_label="— No department —",
        label="Department",
    )

    def __init__(
        self,
        *args,
        role: str,
        department_required: bool = False,
        provisioning_department: Department | None = None,
        **kwargs,
    ):
        self.role = role
        self.department_required = department_required
        self.provisioning_department = provisioning_department
        super().__init__(*args, **kwargs)
        _style_fields(self)
        self.fields["department"].required = department_required
        if department_required:
            self.fields["department"].empty_label = "— Select department —"
        if provisioning_department:
            self.fields["department"].queryset = Department.objects.filter(
                pk=provisioning_department.pk
            )
            self.fields["department"].initial = provisioning_department.pk

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_first_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("first_name", ""),
            field_label="First name",
            required=False,
        )

    def clean_last_name(self):
        from apps.users.name_validation import clean_person_name

        return clean_person_name(
            self.cleaned_data.get("last_name", ""),
            field_label="Last name",
            required=False,
        )

    def save(self) -> User:
        department = self.provisioning_department or self.cleaned_data.get("department")
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            role=self.role,
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
            department=department,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
        )


class CampusProfessorCreateForm(CampusUserCreateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, role=User.Role.PROFESSOR, department_required=False, **kwargs
        )


class CampusChairpersonCreateForm(CampusUserCreateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, role=User.Role.CHAIRPERSON, department_required=True, **kwargs
        )


class CourseOfferingForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "name", "program", "term", "academic_year", "section"]
        widgets = {
            "code": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "MATH101"}
            ),
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "College Algebra"}
            ),
            "program": forms.Select(attrs={"class": INPUT_CLASS}),
            "term": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "1st Sem"}
            ),
            "academic_year": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "2026"}
            ),
            "section": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "BSE 2-1M"}
            ),
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


class ProgramSectionForm(forms.ModelForm):
    class Meta:
        model = ProgramSection
        fields = [
            "program",
            "year_level",
            "label",
            "academic_year",
            "max_students",
            "is_active",
        ]
        widgets = {
            "program": forms.Select(attrs={"class": INPUT_CLASS}),
            "year_level": forms.Select(attrs={"class": INPUT_CLASS}),
            "label": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "1"}),
            "academic_year": forms.Select(attrs={"class": INPUT_CLASS}),
            "max_students": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, coordinator: User | None = None, **kwargs):
        self.coordinator = coordinator
        super().__init__(*args, **kwargs)
        programs = Program.objects.all()
        if coordinator and coordinator.department_id:
            programs = programs.filter(managing_department=coordinator.department)
        self.fields["program"].queryset = programs.order_by("name")
        self.fields["year_level"].queryset = YearLevel.objects.all().order_by("order")
        self.fields["academic_year"].queryset = AcademicYear.objects.all().order_by(
            "-label"
        )
        if not self.instance.pk and not self.initial.get("academic_year"):
            current = get_current_academic_year()
            if current:
                self.fields["academic_year"].initial = current.pk

    def clean_label(self):
        label = (self.cleaned_data.get("label") or "").strip()
        if not label.isdigit():
            raise forms.ValidationError(
                "Section label must be a number (e.g. 1, 2, 3)."
            )
        if int(label) < 1:
            raise forms.ValidationError("Section number must be at least 1.")
        return label


class ProgramSectionBulkForm(forms.Form):
    program = forms.ModelChoiceField(
        queryset=Program.objects.all().order_by("name"),
        label="Program",
    )
    year_level = forms.ModelChoiceField(
        queryset=YearLevel.objects.all().order_by("order"),
        label="Year level",
    )
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by("-label"),
        label="Academic year",
    )
    section_count = forms.IntegerField(
        min_value=1, max_value=50, initial=3, label="Number of sections"
    )
    max_students = forms.IntegerField(
        min_value=1, initial=40, label="Max students per section"
    )

    def __init__(self, *args, coordinator: User | None = None, **kwargs):
        self.coordinator = coordinator
        super().__init__(*args, **kwargs)
        _style_fields(self)
        if coordinator and coordinator.department_id:
            self.fields["program"].queryset = Program.objects.filter(
                managing_department=coordinator.department
            ).order_by("name")
        current = get_current_academic_year()
        if current:
            self.fields["academic_year"].initial = current.pk

    def save(self) -> list[ProgramSection]:
        labels = [str(i + 1) for i in range(self.cleaned_data["section_count"])]
        created = []
        for label in labels:
            section, was_created = ProgramSection.objects.get_or_create(
                program=self.cleaned_data["program"],
                year_level=self.cleaned_data["year_level"],
                academic_year=self.cleaned_data["academic_year"],
                label=label,
                defaults={"max_students": self.cleaned_data["max_students"]},
            )
            if was_created:
                created.append(section)
        return created


class ProgramCoordinatorSubjectForm(forms.Form):
    """Create a curriculum subject within the coordinator's department."""

    program = forms.ModelChoiceField(queryset=Program.objects.none(), label="Program")
    code = forms.CharField(max_length=20, label="Course code")
    name = forms.CharField(max_length=200, label="Course title")
    year_level = forms.ModelChoiceField(
        queryset=YearLevel.objects.none(),
        label="Year level",
    )
    semester = forms.TypedChoiceField(
        choices=Subject.Semester.choices,
        coerce=int,
        label="Semester",
    )

    def __init__(self, *args, coordinator: User, **kwargs):
        self.coordinator = coordinator
        super().__init__(*args, **kwargs)
        _style_fields(self)
        programs = Program.objects.all()
        if coordinator.department_id:
            programs = programs.filter(managing_department=coordinator.department)
        self.fields["program"].queryset = programs.order_by("name")
        self.fields["year_level"].queryset = YearLevel.objects.order_by("order")
        self.fields["code"].widget.attrs["placeholder"] = "e.g. MATH101"
        self.fields["name"].widget.attrs["placeholder"] = "e.g. College Algebra"

    def clean_code(self) -> str:
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        program = cleaned.get("program")
        code = cleaned.get("code")
        if program and code and Subject.objects.filter(program=program, code=code).exists():
            self.add_error("code", f"Course code {code} already exists for this program.")
        return cleaned


class ChairpersonSubjectForm(forms.ModelForm):
    """Add or edit a curriculum subject in the chairperson's department."""

    class Meta:
        model = Subject
        fields = ["program", "code", "name", "year_level", "semester"]

    def __init__(self, *args, manager: User | None = None, **kwargs):
        self.manager = manager
        super().__init__(*args, **kwargs)
        _style_fields(self)
        programs = Program.objects.all()
        if manager is not None and manager.department_id:
            programs = programs.filter(managing_department=manager.department)
        self.fields["program"].queryset = programs.order_by("name")
        self.fields["year_level"].queryset = YearLevel.objects.order_by("order")
        self.fields["code"].widget.attrs["placeholder"] = "e.g. MATH101"
        self.fields["name"].widget.attrs["placeholder"] = "e.g. College Algebra"

    def clean_code(self) -> str:
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        program = cleaned.get("program")
        code = cleaned.get("code")
        if program and code:
            clash = Subject.objects.filter(program=program, code=code)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(
                    "code",
                    f"Course code {code} already exists for this program.",
                )
        return cleaned


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["label", "is_current"]
        widgets = {
            "label": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "2025-2026"}
            ),
            "is_current": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class AcademicTermForm(forms.ModelForm):
    class Meta:
        model = AcademicTerm
        fields = ["academic_year", "name", "semester", "is_current"]
        widgets = {
            "academic_year": forms.Select(attrs={"class": INPUT_CLASS}),
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "1st Sem"}
            ),
            "semester": forms.Select(attrs={"class": INPUT_CLASS}),
            "is_current": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.all().order_by(
            "-label"
        )
        _style_fields(self)


class TeachingAssignmentForm(forms.Form):
    professor = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.PROFESSOR, is_active=True).order_by(
            "email"
        ),
        label="Faculty",
    )
    program_sections = forms.ModelMultipleChoiceField(
        queryset=ProgramSection.queryset_with_counts().select_related(
            "program", "year_level", "academic_year"
        ),
        label="Sections",
        widget=forms.CheckboxSelectMultiple,
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(),
        label="Course",
    )
    term = forms.ModelChoiceField(
        queryset=AcademicTerm.objects.select_related("academic_year").order_by(
            "-academic_year__label", "name"
        ),
        label="Term",
    )

    def __init__(self, *, chairperson: User, **kwargs):
        self.chairperson = chairperson
        super().__init__(**kwargs)
        _style_fields(self)
        self.fields["program_sections"].widget.attrs["class"] = "exam-setup-topic-grid"
        dept_id = chairperson.department_id
        if dept_id:
            self.fields["professor"].queryset = User.objects.filter(
                role=User.Role.PROFESSOR,
                is_active=True,
                department_id=dept_id,
            ).order_by("email")
        elif chairperson.role == User.Role.PROGRAM_COORDINATOR:
            self.fields["professor"].queryset = User.objects.none()
        if dept_id:
            self.fields["program_sections"].queryset = (
                ProgramSection.queryset_with_counts()
                .filter(program__managing_department_id=dept_id, is_active=True)
                .select_related("program", "year_level", "academic_year")
                .order_by("program__name", "year_level__order", "label")
            )
        current_term = AcademicTerm.get_current()
        if current_term:
            self.fields["term"].initial = current_term.pk
        if dept_id:
            from apps.questions.models import Subject

            self.fields["subject"].queryset = (
                Subject.objects.filter(
                    program__managing_department_id=dept_id,
                )
                .select_related("program", "year_level")
                .order_by("program__name", "year_level__order", "code")
            )
        else:
            from apps.questions.models import Subject

            self.fields["subject"].queryset = (
                Subject.objects.all()
                .select_related("program", "year_level")
                .order_by("program__name", "year_level__order", "code")
            )
        section_ids = self.data.getlist("program_sections") if self.data else []
        term_id = self.data.get("term") if self.data else None
        first_section_id = next(
            (sid for sid in section_ids if str(sid).isdigit()),
            None,
        )
        if first_section_id:
            section = (
                ProgramSection.objects.filter(pk=int(first_section_id))
                .select_related("program")
                .first()
            )
            term = None
            if term_id and str(term_id).isdigit():
                term = AcademicTerm.objects.filter(pk=int(term_id)).first()
            if not term:
                term = current_term
            if section and term:
                from apps.questions.curriculum import subjects_for_teaching_assignment

                self.fields["subject"].queryset = subjects_for_teaching_assignment(
                    section, term
                )

    def clean_program_sections(self):
        sections = self.cleaned_data.get("program_sections")
        if not sections:
            raise forms.ValidationError("Select at least one section.")
        return sections

    def clean(self):
        cleaned = super().clean()
        sections = cleaned.get("program_sections")
        subject = cleaned.get("subject")
        term = cleaned.get("term")
        if not sections or not subject:
            return cleaned
        from apps.users.assignment_services import validate_assignment_subject

        for section in sections:
            if subject.program_id != section.program_id:
                raise forms.ValidationError(
                    f"Subject must belong to the program for section {section.label}."
                )
            if term:
                try:
                    validate_assignment_subject(section, subject, term)
                except ValueError as exc:
                    raise forms.ValidationError(str(exc)) from exc
        return cleaned


"""Retired: faculty subject creation moved to the program coordinator.

Kept as a stub so old imports fail loudly instead of silently re-enabling
self-serve subject creation.
"""


class FacultySelfServeCourseForm(forms.Form):
    """Retired — faculty can no longer add subjects."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Only the program coordinator can add subjects.")

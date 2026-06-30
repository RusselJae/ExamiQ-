"""Custom forms for EXAMIQ auth and shared input styling."""

import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from allauth.account.adapter import get_adapter
from allauth.account.forms import ChangePasswordForm, LoginForm, SignupForm
from allauth.account.utils import filter_users_by_email

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
            self.fields["password"].widget.attrs.setdefault("placeholder", "Your password")


class ExamiQSignupForm(SignupForm):
    role = forms.ChoiceField(
        choices=User.Role.choices,
        initial=User.Role.STUDENT,
        label="I am registering as",
        widget=forms.Select(attrs={"class": "auth-role-select-hidden", "id": "id_signup_role", "tabindex": "-1"}),
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
    home_degree_program = forms.ChoiceField(
        choices=[("", "— Select program —")] + list(User.HomeDegreeProgram.choices),
        required=False,
        label="Program",
        widget=forms.Select(attrs={"class": AUTH_SELECT_CLASS, "id": "id_home_degree_program"}),
    )
    year_level = forms.ModelChoiceField(
        queryset=YearLevel.objects.all().order_by("name"),
        required=False,
        empty_label="— Select —",
        label="Year level",
        widget=forms.Select(attrs={"class": AUTH_SELECT_CLASS, "id": "id_year_level"}),
    )
    section = forms.ModelChoiceField(
        queryset=ProgramSection.objects.none(),
        required=False,
        empty_label="— Select section —",
        label="Section",
        widget=forms.Select(attrs={"class": AUTH_SELECT_CLASS, "id": "id_section"}),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by("name"),
        required=False,
        empty_label="— Select department —",
        label="Department",
        widget=forms.Select(attrs={"class": AUTH_SELECT_CLASS, "id": "id_department"}),
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
            self.fields["password2"].widget.attrs.setdefault("placeholder", "Re-enter password")
        self._refresh_section_queryset()

    def _refresh_section_queryset(self) -> None:
        program_slug = self.data.get("home_degree_program") or self.initial.get("home_degree_program", "")
        year_level = self.data.get("year_level") or self.initial.get("year_level")
        year_level_id = int(year_level) if year_level and str(year_level).isdigit() else None
        if program_slug and year_level_id:
            self.fields["section"].queryset = sections_for_student(program_slug, year_level_id)
        else:
            self.fields["section"].queryset = ProgramSection.objects.none()

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
        raise forms.ValidationError("Enter a valid 10-digit mobile number (9XX XXX XXXX).")

    def clean_home_degree_program(self):
        role = self.data.get("role", User.Role.STUDENT)
        value = self.cleaned_data.get("home_degree_program", "")
        if role == User.Role.STUDENT and not value:
            raise forms.ValidationError("Program is required.")
        return value

    def clean_year_level(self):
        role = self.data.get("role", User.Role.STUDENT)
        value = self.cleaned_data.get("year_level")
        if role == User.Role.STUDENT and not value:
            raise forms.ValidationError("Year level is required.")
        return value

    def clean_section(self):
        role = self.data.get("role", User.Role.STUDENT)
        value = self.cleaned_data.get("section")
        if role != User.Role.STUDENT:
            return None
        if not value:
            raise forms.ValidationError("Section is required.")
        program_slug = self.cleaned_data.get("home_degree_program", "")
        year_level = self.cleaned_data.get("year_level")
        if not section_matches_student(value, program_slug, year_level.pk if year_level else None):
            raise forms.ValidationError("Selected section does not match your program and year level.")
        try:
            validate_section_capacity(value)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages[0] if exc.messages else str(exc)) from exc
        return value

    def clean_department(self):
        role = self.data.get("role", User.Role.STUDENT)
        value = self.cleaned_data.get("department")
        if role == User.Role.CHAIRPERSON and not value:
            raise forms.ValidationError("Department is required for chairpersons.")
        return value

    def clean_employee_id(self):
        value = self.cleaned_data.get("employee_id", "").strip()
        role = self.data.get("role", User.Role.STUDENT)
        if role in (User.Role.PROFESSOR, User.Role.CHAIRPERSON) and not value:
            raise forms.ValidationError("Employee ID is required.")
        return value

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role", User.Role.STUDENT)
        if role == User.Role.STUDENT:
            student_number = cleaned.get("student_number")
            if student_number and User.objects.filter(student_number=student_number).exists():
                self.add_error("student_number", "This student number is already registered.")
        return cleaned

    def save(self, request):
        user = super().save(request)
        role = self.cleaned_data["role"]
        user.role = role
        user.phone_number = self.cleaned_data["phone_number"]

        if role == User.Role.STUDENT:
            user.student_number = self.cleaned_data["student_number"]
            user.home_degree_program = self.cleaned_data["home_degree_program"]
            user.year_level = self.cleaned_data["year_level"]
            user.section = self.cleaned_data["section"]
            user.employee_id = ""
            user.approval_status = User.ApprovalStatus.APPROVED
            user.is_active = True
        else:
            user.department = self.cleaned_data.get("department")
            user.employee_id = self.cleaned_data.get("employee_id", "")
            user.student_number = None
            user.approval_status = User.ApprovalStatus.PENDING
            user.is_active = False

        user.save()
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
    section = forms.ModelChoiceField(
        queryset=ProgramSection.objects.none(),
        required=False,
        empty_label="— Select section —",
        label="Section",
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
            del self.fields["section"]
        else:
            self.fields["home_degree_program"].initial = user.home_degree_program
            self.fields["year_level"].initial = user.year_level
            self.fields["section"].initial = user.section
            program_slug = (
                self.data.get("home_degree_program")
                or user.home_degree_program
            )
            year_level = self.data.get("year_level") or (
                str(user.year_level_id) if user.year_level_id else ""
            )
            year_level_id = int(year_level) if str(year_level).isdigit() else None
            if program_slug and year_level_id:
                self.fields["section"].queryset = sections_for_student(
                    program_slug, year_level_id
                )
        _style_fields(self)
        self.fields["profile_photo"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp"

    def clean_section(self):
        section = self.cleaned_data.get("section")
        if self.user.role != User.Role.STUDENT or not section:
            return section
        program_slug = self.cleaned_data.get("home_degree_program", "")
        year_level = self.cleaned_data.get("year_level")
        if not section_matches_student(
            section, program_slug, year_level.pk if year_level else None
        ):
            raise forms.ValidationError("Selected section does not match your program and year level.")
        try:
            validate_section_capacity(section, exclude_user=self.user)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages[0] if exc.messages else str(exc)) from exc
        return section

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
        if self.user.role == User.Role.STUDENT and "section" in self.cleaned_data:
            self.user.section = self.cleaned_data["section"]
            update_fields.append("section")
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
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
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


class ProgramSectionForm(forms.ModelForm):
    class Meta:
        model = ProgramSection
        fields = ["program", "year_level", "label", "academic_year", "max_students", "is_active"]
        widgets = {
            "program": forms.Select(attrs={"class": INPUT_CLASS}),
            "year_level": forms.Select(attrs={"class": INPUT_CLASS}),
            "label": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "1"}),
            "academic_year": forms.Select(attrs={"class": INPUT_CLASS}),
            "max_students": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["program"].queryset = Program.objects.all().order_by("name")
        self.fields["year_level"].queryset = YearLevel.objects.all().order_by("order")
        self.fields["academic_year"].queryset = AcademicYear.objects.all().order_by("-label")
        if not self.instance.pk and not self.initial.get("academic_year"):
            current = get_current_academic_year()
            if current:
                self.fields["academic_year"].initial = current.pk

    def clean_label(self):
        label = (self.cleaned_data.get("label") or "").strip()
        if not label.isdigit():
            raise forms.ValidationError("Section label must be a number (e.g. 1, 2, 3).")
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
    section_count = forms.IntegerField(min_value=1, max_value=50, initial=3, label="Number of sections")
    max_students = forms.IntegerField(min_value=1, initial=40, label="Max students per section")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
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


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["label", "is_current"]
        widgets = {
            "label": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "2025-2026"}),
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
            "name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "1st Sem"}),
            "semester": forms.Select(attrs={"class": INPUT_CLASS}),
            "is_current": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.all().order_by("-label")
        _style_fields(self)


class TeachingAssignmentForm(forms.Form):
    professor = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.PROFESSOR, is_active=True).order_by("email"),
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
        label="Subject",
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

            subject_qs = Subject.objects.filter(
                program__managing_department_id=dept_id,
            ).select_related("program", "year_level")
            if current_term:
                from apps.questions.curriculum import term_semester

                semester = term_semester(current_term)
                if semester is not None:
                    subject_qs = subject_qs.filter(semester=semester)
            self.fields["subject"].queryset = subject_qs.order_by(
                "program__name", "year_level__order", "code"
            )
        section_ids = self.data.getlist("program_sections") if self.data else []
        term_id = self.data.get("term") if self.data else None
        first_section_id = next(
            (sid for sid in section_ids if str(sid).isdigit()),
            None,
        )
        if first_section_id:
            section = ProgramSection.objects.filter(pk=int(first_section_id)).select_related("program").first()
            term = None
            if term_id and str(term_id).isdigit():
                term = AcademicTerm.objects.filter(pk=int(term_id)).first()
            if not term:
                term = current_term
            if section and term:
                from apps.questions.curriculum import subjects_for_teaching_assignment

                self.fields["subject"].queryset = subjects_for_teaching_assignment(section, term)

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

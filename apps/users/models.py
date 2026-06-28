from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Count, Q


class UserManager(BaseUserManager):
    """Custom manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "chairperson")
        return self.create_user(email, password, **extra_fields)


class Department(models.Model):
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Program(models.Model):
    """Degree program — each owns its own math subject topics and question bank."""

    slug = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    managing_department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="managed_programs",
        help_text="Department whose chairperson approves question-bank changes for this program.",
    )

    class Meta:
        verbose_name = "Program"
        verbose_name_plural = "Programs"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def for_home_degree(cls, slug: str):
        """Resolve a Program from a User.home_degree_program slug."""
        if not slug:
            return None
        return cls.objects.filter(slug=slug).first()


class AcademicYear(models.Model):
    """Academic year label, e.g. 2025-2026."""

    label = models.CharField(max_length=20, unique=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"
        ordering = ["-label"]

    def __str__(self) -> str:
        return self.label

    def save(self, *args, **kwargs):
        if self.is_current:
            AcademicYear.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_current(cls) -> "AcademicYear | None":
        return cls.objects.filter(is_current=True).first()


class AcademicTerm(models.Model):
    """Term within an academic year, e.g. 1st Semester."""

    class Semester(models.IntegerChoices):
        FIRST = 1, "1st Semester"
        SECOND = 2, "2nd Semester"

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    name = models.CharField(max_length=50)
    semester = models.PositiveSmallIntegerField(
        choices=Semester.choices,
        default=Semester.FIRST,
    )
    is_current = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Academic Term"
        verbose_name_plural = "Academic Terms"
        ordering = ["academic_year__label", "name"]
        unique_together = [["academic_year", "name"]]

    def __str__(self) -> str:
        return f"{self.name} ({self.academic_year.label})"

    def save(self, *args, **kwargs):
        if self.is_current:
            AcademicTerm.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_current(cls) -> "AcademicTerm | None":
        return cls.objects.filter(is_current=True).select_related("academic_year").first()


class ProgramSection(models.Model):
    """Student cohort section for a program, year level, and academic year."""

    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    year_level = models.ForeignKey(
        "questions.YearLevel",
        on_delete=models.PROTECT,
        related_name="program_sections",
    )
    label = models.CharField(
        max_length=10,
        help_text='Numeric section label, e.g. "1", "2", "3".',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="program_sections",
    )
    max_students = models.PositiveIntegerField(default=40)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Program Section"
        verbose_name_plural = "Program Sections"
        ordering = ["program__name", "year_level__order", "label"]
        unique_together = [["program", "year_level", "label", "academic_year"]]

    def __str__(self) -> str:
        return self.display_label

    @property
    def display_label(self) -> str:
        return (
            f"{self.program.name} · {self.year_level.name} · "
            f"Section {self.label} · {self.academic_year.label}"
        )

    @property
    def student_count(self) -> int:
        if hasattr(self, "_student_count"):
            return self._student_count
        return self.students.filter(role=User.Role.STUDENT).count()

    @property
    def remaining_slots(self) -> int:
        return max(0, self.max_students - self.student_count)

    @property
    def is_full(self) -> bool:
        return self.remaining_slots <= 0

    @classmethod
    def queryset_with_counts(cls):
        return cls.objects.annotate(
            _student_count=Count(
                "students",
                filter=Q(students__role=User.Role.STUDENT),
            )
        )


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        PROFESSOR = "professor", "Faculty"
        CHAIRPERSON = "chairperson", "Department Chairperson"
        CAMPUS_ADMIN = "campus_admin", "Campus Administrator"

    class ApprovalStatus(models.TextChoices):
        APPROVED = "approved", "Approved"
        PENDING = "pending", "Pending"
        REJECTED = "rejected", "Rejected"

    class HomeDegreeProgram(models.TextChoices):
        CS = "cs", "Computer Science"
        IT = "it", "Information Technology"
        BSED_MATH = "bsed_math", "BSEd Mathematics"
        PSYCHOLOGY = "psychology", "Psychology"
        MARKETING = "marketing", "Marketing"
        HR = "hr", "Human Resources"
        HOSPITALITY = "hospitality", "Hospitality Management"
        CRIMINOLOGY = "criminology", "Criminology"

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    home_degree_program = models.CharField(
        max_length=20,
        choices=HomeDegreeProgram.choices,
        blank=True,
        default="",
        help_text="Student's home degree program — scopes review course offerings.",
    )
    year_level = models.ForeignKey(
        "questions.YearLevel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        help_text="Student's current year level — scopes available subjects.",
    )
    section = models.ForeignKey(
        ProgramSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        help_text="Student's cohort section for the current academic year.",
    )
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user last changed their password.",
    )
    middle_name = models.CharField(max_length=150, blank=True, default="")
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    student_number = models.CharField(
        max_length=9,
        unique=True,
        null=True,
        blank=True,
        help_text="Nine-digit student ID (students only).",
    )
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Employee ID for faculty and chairperson accounts.",
    )
    phone_number = models.CharField(
        max_length=11,
        blank=True,
        default="",
        help_text="Eleven-digit mobile number.",
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["email"]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    def get_full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part).strip()

    @property
    def initials(self) -> str:
        parts = [self.first_name[:1], self.last_name[:1]]
        return "".join(p.upper() for p in parts if p) or self.email[:2].upper()

    @property
    def home_program(self):
        """The Program record matching this student's home_degree_program slug."""
        return Program.for_home_degree(self.home_degree_program)


class Course(models.Model):
    """Term course offering — professor-owned, linked to a degree program."""

    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name="course_offerings",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    term = models.CharField(max_length=50, default="1st Sem")
    academic_year = models.CharField(max_length=20, default="2026")
    section = models.CharField(max_length=20, default="A")
    is_archived = models.BooleanField(default=False)
    professor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses_taught",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )

    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"
        ordering = ["-academic_year", "term", "code"]
        unique_together = [["code", "program", "term", "academic_year", "section"]]

    def __str__(self) -> str:
        return f"{self.code}: {self.name} ({self.term} {self.academic_year})"

    @property
    def display_label(self) -> str:
        """Human-readable label for student course-offering selection."""
        prof = self.professor.get_full_name() if self.professor else "TBA"
        section_part = f"Sec {self.section}, " if self.section else ""
        return f"{self.code} {self.name}, {section_part}{prof}, {self.term} {self.academic_year}"


class Enrollment(models.Model):
    """Legacy enrollment — retained for demo data; sessions use course-offering selection."""

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": User.Role.STUDENT},
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Enrollment"
        verbose_name_plural = "Enrollments"
        ordering = ["-enrolled_at"]
        unique_together = [["student", "course"]]

    def __str__(self) -> str:
        return f"{self.student.email} in {self.course.code}"


class TeachingAssignment(models.Model):
    """Chairperson-assigned teaching load for a faculty member."""

    professor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
        limit_choices_to={"role": User.Role.PROFESSOR},
    )
    program_section = models.ForeignKey(
        ProgramSection,
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
    )
    subject = models.ForeignKey(
        "questions.Subject",
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
    )
    term = models.ForeignKey(
        AcademicTerm,
        on_delete=models.PROTECT,
        related_name="teaching_assignments",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_created",
        limit_choices_to={"role": User.Role.CHAIRPERSON},
    )
    course = models.OneToOneField(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_assignment",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Teaching Assignment"
        verbose_name_plural = "Teaching Assignments"
        ordering = ["-term__academic_year__label", "term__name", "program_section__label"]
        unique_together = [
            ["professor", "program_section", "subject", "term"],
        ]

    def __str__(self) -> str:
        return (
            f"{self.professor.email} — {self.subject.code} — "
            f"{self.program_section.display_label}"
        )


class Notification(models.Model):
    """In-app notification for account and workflow events."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=500, blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.email}: {self.message[:50]}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if not self.read_at:
            from django.utils import timezone

            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        PROFESSOR = "professor", "Professor"
        CHAIRPERSON = "chairperson", "Department Chairperson"

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
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user last changed their password.",
    )
    middle_name = models.CharField(max_length=150, blank=True, default="")
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)

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
        return f"{self.code} {self.name}, {prof}, {self.term} {self.academic_year}"


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

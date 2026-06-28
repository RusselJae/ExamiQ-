from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import (
    AcademicTerm,
    AcademicYear,
    Course,
    Department,
    Enrollment,
    Notification,
    Program,
    ProgramSection,
    TeachingAssignment,
    User,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "managing_department"]
    list_filter = ["managing_department"]
    search_fields = ["name", "slug"]
    ordering = ["name"]


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["label", "is_current"]
    list_filter = ["is_current"]
    ordering = ["-label"]


@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ["name", "academic_year", "is_current"]
    list_filter = ["academic_year", "is_current"]
    ordering = ["-academic_year__label", "name"]


@admin.register(ProgramSection)
class ProgramSectionAdmin(admin.ModelAdmin):
    list_display = ["display_label", "max_students", "is_active"]
    list_filter = ["program", "year_level", "academic_year", "is_active"]
    search_fields = ["label", "program__name"]
    ordering = ["program__name", "year_level__order", "label"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "email",
        "first_name",
        "last_name",
        "role",
        "department",
        "home_degree_program",
        "section",
        "approval_status",
        "is_staff",
    ]
    list_filter = [
        "role",
        "department",
        "home_degree_program",
        "approval_status",
        "is_staff",
        "is_active",
    ]
    search_fields = ["email", "first_name", "last_name", "student_number"]
    ordering = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "department",
                    "home_degree_program",
                    "year_level",
                    "section",
                )
            },
        ),
        ("Role", {"fields": ("role", "approval_status", "employee_id", "student_number")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "role",
                    "department",
                    "home_degree_program",
                    "year_level",
                    "section",
                ),
            },
        ),
    )


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "program", "term", "academic_year", "section", "professor", "is_archived"]
    list_filter = ["program", "term", "academic_year", "is_archived"]
    search_fields = ["code", "name", "professor__email"]
    ordering = ["-academic_year", "term", "code"]


@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(admin.ModelAdmin):
    list_display = ["professor", "program_section", "subject", "term", "assigned_by"]
    list_filter = ["term__academic_year", "term"]
    search_fields = ["professor__email", "subject__code"]
    ordering = ["-term__academic_year__label", "term__name"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "message", "read_at", "created_at"]
    list_filter = ["read_at"]
    search_fields = ["user__email", "message"]
    ordering = ["-created_at"]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student", "course", "enrolled_at"]
    list_filter = ["course__program"]
    search_fields = ["student__email", "course__code"]
    ordering = ["-enrolled_at"]

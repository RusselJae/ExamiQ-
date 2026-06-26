from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import Course, Department, Enrollment, Program, User


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


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "first_name", "last_name", "role", "department", "home_degree_program", "is_staff"]
    list_filter = ["role", "department", "home_degree_program", "is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "department", "home_degree_program")}),
        ("Role", {"fields": ("role",)}),
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
                "fields": ("email", "password1", "password2", "role", "department", "home_degree_program"),
            },
        ),
    )


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "program", "term", "academic_year", "section", "professor", "is_archived"]
    list_filter = ["program", "term", "academic_year", "is_archived"]
    search_fields = ["code", "name", "professor__email"]
    ordering = ["-academic_year", "term", "code"]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student", "course", "enrolled_at"]
    list_filter = ["course__program"]
    search_fields = ["student__email", "course__code"]
    ordering = ["-enrolled_at"]

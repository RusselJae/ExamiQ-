from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0024_alter_teachingassignment_assigned_by_alter_user_role_and_more"),
        # Pinned (was "__latest__") so later questions migrations do not
        # retroactively reorder this already-applied migration.
        ("questions", "0015_excludedquestion"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="academic_year",
            field=models.ForeignKey(
                blank=True,
                help_text="Official year standing for admin purposes (tuition, graduation).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="students_by_academic_year",
                to="questions.YearLevel",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="is_irregular",
            field=models.BooleanField(
                default=False,
                help_text="Irregular student — not bound to a single cohort section.",
            ),
        ),
        migrations.CreateModel(
            name="IrregularSubjectEnrollment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("enrolled", "Enrolled"),
                            ("dropped", "Dropped"),
                            ("completed", "Completed"),
                        ],
                        default="enrolled",
                        max_length=20,
                    ),
                ),
                (
                    "enrolled_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="irregular_students",
                        to="users.programsection",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="irregular_enrollments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "subject",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="irregular_enrollments",
                        to="questions.subject",
                    ),
                ),
                (
                    "term",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="irregular_enrollments",
                        to="users.academicterm",
                    ),
                ),
            ],
            options={
                "verbose_name": "Irregular Subject Enrollment",
                "verbose_name_plural": "Irregular Subject Enrollments",
                "ordering": ["-enrolled_at"],
                "unique_together": {("student", "subject", "term")},
            },
        ),
    ]

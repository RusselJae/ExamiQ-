import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_role", models.CharField(blank=True, max_length=32)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("login", "Login"),
                            ("assignment_create", "Assignment created"),
                            ("assignment_delete", "Assignment deleted"),
                            ("question_create", "Question created"),
                            ("question_update", "Question updated"),
                            ("question_toggle", "Question active toggled"),
                            ("session_start", "Exam session started"),
                            ("session_complete", "Exam session completed"),
                            ("user_approve", "User approved"),
                            ("user_reject", "User rejected"),
                            ("exam_setup_save", "Exam setup saved"),
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                ("target_type", models.CharField(blank=True, max_length=64)),
                ("target_id", models.PositiveIntegerField(blank=True, null=True)),
                ("message", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events_about",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Audit log",
                "verbose_name_plural": "Audit logs",
                "ordering": ["-created_at"],
            },
        ),
    ]

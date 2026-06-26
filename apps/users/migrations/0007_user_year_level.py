"""Add year_level FK to User for student subject scoping."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("questions", "0006_curriculum_hierarchy"),
        ("users", "0006_user_password_changed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="year_level",
            field=models.ForeignKey(
                blank=True,
                help_text="Student's current year level — scopes available subjects.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="students",
                to="questions.yearlevel",
            ),
        ),
    ]

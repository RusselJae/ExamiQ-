# Generated manually for faculty signup PIN profile management.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0020_email_signup_otp"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacultySignupPinSettings",
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
                ("pin_hash", models.CharField(blank=True, default="", max_length=128)),
                ("updated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="faculty_signup_pin_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Faculty signup PIN",
                "verbose_name_plural": "Faculty signup PIN",
            },
        ),
    ]

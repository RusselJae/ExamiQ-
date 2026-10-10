# Generated for password-reset throttling, login fingerprints, and name length.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0021_faculty_signup_pin_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="middle_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.CreateModel(
            name="PasswordResetRequestLog",
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
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("requested_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, null=True),
                ),
            ],
            options={
                "verbose_name": "Password reset request",
                "verbose_name_plural": "Password reset requests",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.CreateModel(
            name="UserLoginFingerprint",
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
                    "ip_address",
                    models.GenericIPAddressField(blank=True, null=True),
                ),
                ("user_agent_hash", models.CharField(max_length=64)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="login_fingerprints",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Login fingerprint",
                "verbose_name_plural": "Login fingerprints",
                "ordering": ["-last_seen_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "ip_address", "user_agent_hash"),
                        name="uniq_user_login_fingerprint",
                    )
                ],
            },
        ),
    ]

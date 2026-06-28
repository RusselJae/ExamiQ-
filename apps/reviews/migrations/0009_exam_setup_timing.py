from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0008_exam_setup_overhaul"),
    ]

    operations = [
        migrations.AddField(
            model_name="examsetup",
            name="duration_minutes",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Total exam session length in minutes.",
            ),
        ),
        migrations.AddField(
            model_name="examsetup",
            name="seconds_per_question",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Time limit per question in timed exam mode.",
            ),
        ),
    ]

"""Review session timed exam fields and nullable answer confidence."""

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0004_answer_confidence_1_to_5"),
        ("questions", "0006_curriculum_hierarchy"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewwindow",
            name="mode",
            field=models.CharField(
                choices=[
                    ("timed_exam", "Timed Exam"),
                    ("practice_review", "Practice Review"),
                ],
                default="timed_exam",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="reviewwindow",
            name="seconds_per_question",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Time limit per question in timed exam mode.",
            ),
        ),
        migrations.AddField(
            model_name="reviewsession",
            name="mode",
            field=models.CharField(
                choices=[
                    ("timed_exam", "Timed Exam"),
                    ("practice_review", "Practice Review"),
                ],
                default="timed_exam",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="reviewsession",
            name="seconds_per_question",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name="answer",
            name="timed_out",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="answer",
            name="confidence",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Student confidence level from 1 (low) to 5 (high).",
                null=True,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="answer",
            name="answer_confidence_range",
        ),
        migrations.AddConstraint(
            model_name="answer",
            constraint=models.CheckConstraint(
                condition=Q(confidence__isnull=True)
                | (Q(confidence__gte=1) & Q(confidence__lte=5)),
                name="answer_confidence_range",
            ),
        ),
    ]

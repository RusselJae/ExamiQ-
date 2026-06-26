# Confidence scale expanded to 1-5

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0003_reviewwindow_stepfeedbackview_reviewsession_course_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="answer",
            name="answer_confidence_tier",
        ),
        migrations.AlterField(
            model_name="answer",
            name="confidence",
            field=models.PositiveSmallIntegerField(
                help_text="Student confidence level from 1 (low) to 5 (high).",
            ),
        ),
        migrations.AddConstraint(
            model_name="answer",
            constraint=models.CheckConstraint(
                condition=Q(confidence__gte=1) & Q(confidence__lte=5),
                name="answer_confidence_range",
            ),
        ),
    ]

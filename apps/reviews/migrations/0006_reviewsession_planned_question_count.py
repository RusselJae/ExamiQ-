"""Add planned_question_count to ReviewSession."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0005_timed_exam_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewsession",
            name="planned_question_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]

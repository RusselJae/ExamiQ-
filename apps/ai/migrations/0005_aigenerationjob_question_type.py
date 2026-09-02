from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0004_aigenerationjob_explanation_generate"),
    ]

    operations = [
        migrations.AddField(
            model_name="aigenerationjob",
            name="question_type",
            field=models.CharField(
                blank=True,
                default="mcq",
                help_text="Single question type for this generation job.",
                max_length=20,
            ),
        ),
    ]

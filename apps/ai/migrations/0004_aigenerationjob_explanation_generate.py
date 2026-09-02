from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0003_learning_document_chunks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aigenerationjob",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("question_generate", "Question generate"),
                    ("explanation_generate", "Explanation generate"),
                ],
                default="question_generate",
                max_length=40,
            ),
        ),
    ]

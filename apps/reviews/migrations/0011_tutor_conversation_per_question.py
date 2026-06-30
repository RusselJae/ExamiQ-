# Generated manually for per-question tutor conversations

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def clear_tutor_data(apps, schema_editor):
    TutorMessage = apps.get_model("reviews", "TutorMessage")
    TutorConversation = apps.get_model("reviews", "TutorConversation")
    TutorMessage.objects.all().delete()
    TutorConversation.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("questions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reviews", "0010_tutor_conversation"),
    ]

    operations = [
        migrations.RunPython(clear_tutor_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="tutorconversation",
            name="session",
        ),
        migrations.RemoveField(
            model_name="tutorconversation",
            name="active_answer",
        ),
        migrations.AddField(
            model_name="tutorconversation",
            name="student",
            field=models.ForeignKey(
                limit_choices_to={"role": "student"},
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tutor_conversations",
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="tutorconversation",
            name="question",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tutor_conversations",
                to="questions.question",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="tutorconversation",
            constraint=models.UniqueConstraint(
                fields=("student", "question"),
                name="unique_tutor_conversation_per_student_question",
            ),
        ),
    ]

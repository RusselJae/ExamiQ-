from django.db import migrations


def approve_pending_questions(apps, schema_editor):
    Question = apps.get_model("questions", "Question")
    Question.objects.filter(status="pending").update(status="approved")


class Migration(migrations.Migration):
    dependencies = [
        ("questions", "0007_alter_question_difficulty"),
    ]

    operations = [
        migrations.RunPython(approve_pending_questions, migrations.RunPython.noop),
    ]

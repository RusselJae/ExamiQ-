"""Migrate per-mistake concern messages into per-student chat threads."""

from django.db import migrations
from django.utils import timezone


def migrate_concern_messages_to_chat(apps, schema_editor):
    MistakeRecord = apps.get_model("analytics", "MistakeRecord")
    MistakeConcernMessage = apps.get_model("analytics", "MistakeConcernMessage")
    StudentFacultyConversation = apps.get_model(
        "analytics", "StudentFacultyConversation"
    )
    StudentFacultyMessage = apps.get_model("analytics", "StudentFacultyMessage")

    student_ids = (
        MistakeConcernMessage.objects.values_list(
            "mistake_record__student_id", flat=True
        )
        .distinct()
    )
    for student_id in student_ids:
        if not student_id:
            continue
        conversation, _ = StudentFacultyConversation.objects.get_or_create(
            student_id=student_id,
        )
        faculty_ids: set[int] = set()
        for record in MistakeRecord.objects.filter(student_id=student_id):
            faculty_ids.update(
                record.concern_faculty.values_list("pk", flat=True)
            )
        if faculty_ids:
            conversation.participating_faculty.add(*faculty_ids)

        concern_messages = (
            MistakeConcernMessage.objects.filter(mistake_record__student_id=student_id)
            .select_related("author")
            .order_by("created_at")
        )
        last_at = None
        for msg in concern_messages:
            StudentFacultyMessage.objects.create(
                conversation=conversation,
                author_id=msg.author_id,
                body=msg.body or "",
                image=msg.image,
                created_at=msg.created_at or timezone.now(),
            )
            last_at = msg.created_at
        if last_at:
            conversation.last_message_at = last_at
            conversation.save(update_fields=["last_message_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0010_student_faculty_chat"),
    ]

    operations = [
        migrations.RunPython(migrate_concern_messages_to_chat, noop_reverse),
    ]

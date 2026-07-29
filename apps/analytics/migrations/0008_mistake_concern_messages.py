# Generated manually for concern message threading

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_concern_messages(apps, schema_editor):
    MistakeRecord = apps.get_model("analytics", "MistakeRecord")
    MistakeConcernMessage = apps.get_model("analytics", "MistakeConcernMessage")
    Course = apps.get_model("users", "Course")

    for record in MistakeRecord.objects.select_related("student").iterator():
        if (record.student_note or "").strip() or record.student_image:
            MistakeConcernMessage.objects.create(
                mistake_record_id=record.pk,
                author_id=record.student_id,
                body=record.student_note or "",
                image=record.student_image,
                created_at=record.occurred_at,
            )

        faculty_note = (record.faculty_note or "").strip()
        if not faculty_note:
            continue

        faculty_id = None
        try:
            Question = apps.get_model("questions", "Question")
            question = Question.objects.select_related("topic__subject").get(
                pk=record.question_id
            )
            subject = question.topic.subject
            course = Course.objects.filter(
                code=subject.code,
                program_id=subject.program_id,
                professor__isnull=False,
            ).first()
            if course:
                faculty_id = course.professor_id
        except Exception:
            faculty_id = None

        if not faculty_id:
            User = apps.get_model("users", "User")
            fallback = User.objects.filter(role="PROFESSOR").order_by("pk").first()
            faculty_id = fallback.pk if fallback else record.student_id

        MistakeConcernMessage.objects.create(
            mistake_record_id=record.pk,
            author_id=faculty_id,
            body=faculty_note,
            created_at=record.faculty_noted_at or record.occurred_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0007_mistake_record_faculty_note"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="mistakerecord",
            name="faculty_viewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="MistakeConcernMessage",
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
                ("body", models.TextField(blank=True)),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="mistake_concerns/%Y/%m/",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="concern_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "mistake_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="concern_messages",
                        to="analytics.mistakerecord",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mistake Concern Message",
                "verbose_name_plural": "Mistake Concern Messages",
                "ordering": ["created_at"],
            },
        ),
        migrations.RunPython(backfill_concern_messages, migrations.RunPython.noop),
    ]

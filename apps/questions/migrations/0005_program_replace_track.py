# Generated manually — Topic.track → Topic.program

import django.db.models.deletion
from django.db import migrations, models


def migrate_topics_to_programs(apps, schema_editor):
    Topic = apps.get_model("questions", "Topic")
    Program = apps.get_model("users", "Program")
    OldTrack = apps.get_model("users", "OldTrack")

    programs_by_slug = {p.slug: p for p in Program.objects.all()}
    if not programs_by_slug:
        return

    track_to_program = {}
    major = OldTrack.objects.filter(kind="major").first()
    gen_ed = OldTrack.objects.filter(kind="general_ed").first()
    if major:
        track_to_program[major.pk] = programs_by_slug.get("bsed_math")
    if gen_ed:
        track_to_program[gen_ed.pk] = programs_by_slug.get("cs")

    default_program = programs_by_slug.get("cs") or Program.objects.first()
    for topic in Topic.objects.all():
        if topic.track_id and topic.track_id in track_to_program and track_to_program[topic.track_id]:
            topic.program_id = track_to_program[topic.track_id].pk
        else:
            topic.program_id = default_program.pk
        topic.save(update_fields=["program_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("questions", "0004_v2_alignment"),
        ("users", "0004_program_replace_track"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="topic",
                    name="track",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="topics",
                        to="users.oldtrack",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="topic",
            name="program",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topics",
                to="users.program",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="topic",
            unique_together=set(),
        ),
        migrations.RunPython(migrate_topics_to_programs, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="topic",
            name="track",
        ),
        migrations.AlterField(
            model_name="topic",
            name="program",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topics",
                to="users.program",
            ),
        ),
        migrations.AlterModelOptions(
            name="topic",
            options={"ordering": ["program__name", "name"], "verbose_name": "Topic", "verbose_name_plural": "Topics"},
        ),
        migrations.AlterUniqueTogether(
            name="topic",
            unique_together={("program", "name")},
        ),
    ]

# Generated manually for ExamiQ v2 alignment

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_topics_to_tracks(apps, schema_editor):
  Topic = apps.get_model("questions", "Topic")
  Program = apps.get_model("users", "Program")
  Track = apps.get_model("users", "Track")

  gen_ed = Track.objects.filter(kind="general_ed").first()
  major = Track.objects.filter(kind="major").first()
  if not gen_ed:
    return

  program_track_map = {}
  for program in Program.objects.all():
    name_lower = program.name.lower()
    if "bsed" in name_lower or "education" in name_lower or "major" in name_lower:
      program_track_map[program.pk] = major.pk if major else gen_ed.pk
    else:
      program_track_map[program.pk] = gen_ed.pk

  for topic in Topic.objects.all():
    if topic.program_id and topic.program_id in program_track_map:
      topic.track_id = program_track_map[topic.program_id]
    else:
      topic.track_id = gen_ed.pk
    topic.save(update_fields=["track_id"])


class Migration(migrations.Migration):

  dependencies = [
    ("questions", "0003_explanationstep_professor_note_and_more"),
    ("users", "0003_v2_alignment"),
  ]

  operations = [
    migrations.AddField(
      model_name="question",
      name="proposed_by",
      field=models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="proposed_questions",
        to=settings.AUTH_USER_MODEL,
      ),
    ),
    migrations.AddField(
      model_name="question",
      name="rejection_note",
      field=models.TextField(blank=True),
    ),
    migrations.AddField(
      model_name="question",
      name="reviewed_at",
      field=models.DateTimeField(blank=True, null=True),
    ),
    migrations.AddField(
      model_name="question",
      name="reviewed_by",
      field=models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="reviewed_questions",
        to=settings.AUTH_USER_MODEL,
      ),
    ),
    migrations.AddField(
      model_name="question",
      name="status",
      field=models.CharField(
        choices=[
          ("draft", "Draft"),
          ("pending", "Pending Review"),
          ("approved", "Approved"),
          ("rejected", "Rejected"),
        ],
        default="approved",
        max_length=20,
      ),
    ),
    migrations.AddField(
      model_name="topic",
      name="track",
      field=models.ForeignKey(
        null=True,
        on_delete=django.db.models.deletion.CASCADE,
        related_name="topics",
        to="users.track",
      ),
    ),
    migrations.RunPython(migrate_topics_to_tracks, migrations.RunPython.noop),
    migrations.AlterUniqueTogether(
      name="topic",
      unique_together=set(),
    ),
    migrations.RemoveField(
      model_name="topic",
      name="program",
    ),
    migrations.AlterField(
      model_name="topic",
      name="track",
      field=models.ForeignKey(
        on_delete=django.db.models.deletion.CASCADE,
        related_name="topics",
        to="users.track",
      ),
    ),
    migrations.AlterModelOptions(
      name="topic",
      options={"ordering": ["track__name", "name"], "verbose_name": "Topic", "verbose_name_plural": "Topics"},
    ),
    migrations.AlterUniqueTogether(
      name="topic",
      unique_together={("track", "name")},
    ),
  ]

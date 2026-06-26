# Generated manually for ExamiQ v2 alignment

import django.db.models.deletion
from django.db import migrations, models


def seed_tracks_and_migrate_courses(apps, schema_editor):
  Department = apps.get_model("users", "Department")
  Track = apps.get_model("users", "Track")
  Program = apps.get_model("users", "Program")
  Course = apps.get_model("users", "Course")

  # Ensure a managing department exists for track approval
  edu_dept, _ = Department.objects.get_or_create(name="College of Education")
  math_dept, _ = Department.objects.get_or_create(name="Mathematics Department")

  gen_ed, _ = Track.objects.get_or_create(
    kind="general_ed",
    name="General Education Math",
    defaults={"managing_department_id": edu_dept.pk},
  )
  major, _ = Track.objects.get_or_create(
    kind="major",
    name="Math Major (BSEd)",
    defaults={"managing_department_id": edu_dept.pk},
  )

  program_track_map = {}
  for program in Program.objects.all():
    name_lower = program.name.lower()
    if "bsed" in name_lower or "education" in name_lower or "major" in name_lower:
      program_track_map[program.pk] = major.pk
    else:
      program_track_map[program.pk] = gen_ed.pk

  for course in Course.objects.all():
    if course.program_id and course.program_id in program_track_map:
      course.track_id = program_track_map[course.program_id]
    else:
      course.track_id = gen_ed.pk
    if not course.term:
      course.term = "1st Sem"
    if not course.academic_year:
      course.academic_year = "2026"
    if not course.section:
      course.section = "A"
    course.save(update_fields=["track_id", "term", "academic_year", "section"])


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
    ("users", "0002_alter_user_managers"),
  ]

  operations = [
    migrations.CreateModel(
      name="Track",
      fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("name", models.CharField(max_length=200)),
        (
          "kind",
          models.CharField(
            choices=[("general_ed", "General Education Math"), ("major", "Math Major (BSEd)")],
            max_length=20,
          ),
        ),
        (
          "managing_department",
          models.ForeignKey(
            help_text="Department whose chairperson approves question-bank changes for this track.",
            on_delete=django.db.models.deletion.PROTECT,
            related_name="managed_tracks",
            to="users.department",
          ),
        ),
      ],
      options={
        "verbose_name": "Track",
        "verbose_name_plural": "Tracks",
        "ordering": ["name"],
        "unique_together": {("kind", "name")},
      },
    ),
    migrations.AddField(
      model_name="user",
      name="home_degree_program",
      field=models.CharField(
        blank=True,
        choices=[
          ("cs", "Computer Science"),
          ("it", "Information Technology"),
          ("bsed_math", "BSEd Mathematics"),
          ("psychology", "Psychology"),
          ("marketing", "Marketing"),
          ("hr", "Human Resources"),
          ("hospitality", "Hospitality Management"),
          ("criminology", "Criminology"),
        ],
        default="",
        help_text="Student's home degree program — analytics metadata only.",
        max_length=20,
      ),
    ),
    migrations.AddField(
      model_name="course",
      name="academic_year",
      field=models.CharField(default="2026", max_length=20),
    ),
    migrations.AddField(
      model_name="course",
      name="is_archived",
      field=models.BooleanField(default=False),
    ),
    migrations.AddField(
      model_name="course",
      name="section",
      field=models.CharField(default="A", max_length=20),
    ),
    migrations.AddField(
      model_name="course",
      name="term",
      field=models.CharField(default="1st Sem", max_length=50),
    ),
    migrations.AddField(
      model_name="course",
      name="track",
      field=models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.PROTECT,
        related_name="course_offerings",
        to="users.track",
      ),
    ),
    migrations.AlterField(
      model_name="course",
      name="program",
      field=models.ForeignKey(
        blank=True,
        help_text="Deprecated — use track for content scope.",
        null=True,
        on_delete=django.db.models.deletion.CASCADE,
        related_name="courses",
        to="users.program",
      ),
    ),
    migrations.AlterModelOptions(
      name="course",
      options={"ordering": ["-academic_year", "term", "code"], "verbose_name": "Course", "verbose_name_plural": "Courses"},
    ),
    migrations.AlterUniqueTogether(
      name="course",
      unique_together={("code", "track", "term", "academic_year", "section")},
    ),
    migrations.RunPython(seed_tracks_and_migrate_courses, migrations.RunPython.noop),
  ]

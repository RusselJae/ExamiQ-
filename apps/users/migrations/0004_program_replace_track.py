# Generated manually — replace Track/Legacy Program with degree Program model

import django.db.models.deletion
from django.db import migrations, models


PROGRAM_DEFINITIONS = [
    ("cs", "Computer Science", "Computer Science"),
    ("it", "Information Technology", "Information Technology"),
    ("bsed_math", "BSEd Mathematics", "College of Education"),
    ("psychology", "Psychology", "Psychology"),
    ("marketing", "Marketing", "Business Administration"),
    ("hr", "Human Resources", "Business Administration"),
    ("hospitality", "Hospitality Management", "Hospitality Management"),
    ("criminology", "Criminology", "Criminology"),
]


def seed_programs_and_migrate_courses(apps, schema_editor):
    Department = apps.get_model("users", "Department")
    Program = apps.get_model("users", "Program")
    OldTrack = apps.get_model("users", "OldTrack")
    Course = apps.get_model("users", "Course")

    programs_by_slug = {}
    for slug, name, dept_name in PROGRAM_DEFINITIONS:
        dept, _ = Department.objects.get_or_create(name=dept_name)
        prog, _ = Program.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "managing_department_id": dept.pk},
        )
        programs_by_slug[slug] = prog

    track_to_program = {}
    major = OldTrack.objects.filter(kind="major").first()
    gen_ed = OldTrack.objects.filter(kind="general_ed").first()
    if major:
        track_to_program[major.pk] = programs_by_slug["bsed_math"]
    if gen_ed:
        track_to_program[gen_ed.pk] = programs_by_slug["cs"]

    default_program = programs_by_slug["cs"]
    for course in Course.objects.all():
        if course.track_id and course.track_id in track_to_program:
            course.program_id = track_to_program[course.track_id].pk
        else:
            course.program_id = default_program.pk
        course.save(update_fields=["program_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_v2_alignment"),
        ("questions", "0004_v2_alignment"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="course",
            name="program",
        ),
        migrations.DeleteModel(
            name="Program",
        ),
        migrations.RenameModel(
            old_name="Track",
            new_name="OldTrack",
        ),
        migrations.CreateModel(
            name="Program",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=30, unique=True)),
                ("name", models.CharField(max_length=200)),
                (
                    "managing_department",
                    models.ForeignKey(
                        help_text="Department whose chairperson approves question-bank changes for this program.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="managed_programs",
                        to="users.department",
                    ),
                ),
            ],
            options={
                "verbose_name": "Program",
                "verbose_name_plural": "Programs",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="course",
            name="program",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="course_offerings",
                to="users.program",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="course",
            unique_together=set(),
        ),
        migrations.RunPython(seed_programs_and_migrate_courses, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="course",
            name="track",
        ),
        migrations.AlterField(
            model_name="course",
            name="program",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="course_offerings",
                to="users.program",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="course",
            unique_together={("code", "program", "term", "academic_year", "section")},
        ),
    ]

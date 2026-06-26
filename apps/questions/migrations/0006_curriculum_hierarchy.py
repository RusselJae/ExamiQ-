"""Curriculum hierarchy: YearLevel, Subject; Topic.program -> Topic.subject."""

from django.db import migrations, models
import django.db.models.deletion
import model_utils.fields
import django.utils.timezone


def seed_year_levels(apps, schema_editor):
    YearLevel = apps.get_model("questions", "YearLevel")
    for order, name in enumerate(
        ["1st Year", "2nd Year", "3rd Year", "4th Year"],
        start=1,
    ):
        YearLevel.objects.get_or_create(order=order, defaults={"name": name})


def migrate_topics_to_subjects(apps, schema_editor):
    Topic = apps.get_model("questions", "Topic")
    Subject = apps.get_model("questions", "Subject")
    YearLevel = apps.get_model("questions", "YearLevel")
    Program = apps.get_model("users", "Program")

    default_year = YearLevel.objects.filter(order=1).first()
    if not default_year:
        return

    for program in Program.objects.all():
        placeholder, _ = Subject.objects.get_or_create(
            program=program,
            code=f"GEN-{program.slug.upper()}",
            defaults={
                "year_level": default_year,
                "semester": 1,
                "name": f"General Mathematics ({program.name})",
            },
        )
        Topic.objects.filter(program_id=program.pk).update(subject_id=placeholder.pk)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_delete_oldtrack"),
        ("questions", "0005_program_replace_track"),
    ]

    operations = [
        migrations.CreateModel(
            name="YearLevel",
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
                ("order", models.PositiveSmallIntegerField(unique=True)),
                ("name", models.CharField(max_length=50)),
            ],
            options={
                "verbose_name": "Year Level",
                "verbose_name_plural": "Year Levels",
                "ordering": ["order"],
            },
        ),
        migrations.RunPython(seed_year_levels, noop),
        migrations.CreateModel(
            name="Subject",
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
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                ("semester", models.PositiveSmallIntegerField(choices=[(1, "1st Semester"), (2, "2nd Semester")])),
                ("code", models.CharField(max_length=20)),
                ("name", models.CharField(max_length=200)),
                (
                    "program",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subjects",
                        to="users.program",
                    ),
                ),
                (
                    "year_level",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subjects",
                        to="questions.yearlevel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Subject",
                "verbose_name_plural": "Subjects",
                "ordering": ["program__name", "year_level__order", "semester", "code"],
                "unique_together": {("program", "code")},
            },
        ),
        migrations.AddField(
            model_name="question",
            name="concept_tag",
            field=models.CharField(
                blank=True,
                help_text="Short concept label or AI-generated explanation summary.",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="topic",
            name="subject",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topics",
                to="questions.subject",
            ),
        ),
        migrations.RunPython(migrate_topics_to_subjects, noop),
        migrations.AlterField(
            model_name="topic",
            name="subject",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topics",
                to="questions.subject",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="topic",
            unique_together={("subject", "name")},
        ),
        migrations.RemoveField(
            model_name="topic",
            name="program",
        ),
        migrations.AlterModelOptions(
            name="topic",
            options={
                "ordering": ["subject__code", "name"],
                "verbose_name": "Topic",
                "verbose_name_plural": "Topics",
            },
        ),
    ]

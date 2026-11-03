"""Collapse duplicate teaching assignments to one row per faculty + course.

One faculty handles a course once per term: when several rows exist for the
same (professor, subject, term) — e.g. one per section — keep the earliest
and delete the rest so the unique load constraint can land cleanly.
"""

from django.db import migrations


def collapse_duplicates(apps, schema_editor):
    TeachingAssignment = apps.get_model("users", "TeachingAssignment")
    seen = {}
    for pk, professor_id, subject_id, term_id in (
        TeachingAssignment.objects.order_by("pk").values_list(
            "pk", "professor_id", "subject_id", "term_id"
        )
    ):
        key = (professor_id, subject_id, term_id)
        if key in seen:
            continue
        seen[key] = pk
    TeachingAssignment.objects.exclude(pk__in=seen.values()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0027_corupload_pendingstudentregistration"),
    ]

    operations = [
        migrations.RunPython(
            collapse_duplicates, reverse_code=migrations.RunPython.noop
        ),
    ]

from django.db import migrations

PLACEHOLDER_MIDDLE_NAMES = ("n/a", "none", "null", "-")


def clear_placeholder_middle_names(apps, schema_editor):
    """Treat stored N/A-style middle names as an empty optional field."""
    User = apps.get_model("users", "User")
    values = list(
        User.objects.exclude(middle_name="")
        .values_list("middle_name", flat=True)
        .distinct()
    )
    for value in values:
        if (value or "").strip().casefold() in PLACEHOLDER_MIDDLE_NAMES:
            User.objects.filter(middle_name=value).update(middle_name="")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0032_alter_user_home_degree_program"),
    ]

    operations = [
        migrations.RunPython(
            clear_placeholder_middle_names,
            migrations.RunPython.noop,
        ),
    ]

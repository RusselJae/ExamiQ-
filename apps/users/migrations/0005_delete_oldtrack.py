# Drop legacy OldTrack after Topic.program migration

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_program_replace_track"),
        ("questions", "0005_program_replace_track"),
    ]

    operations = [
        migrations.DeleteModel(
            name="OldTrack",
        ),
    ]

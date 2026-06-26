from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_delete_oldtrack"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="password_changed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user last changed their password.",
                null=True,
            ),
        ),
    ]

# Generated manually: allow a faculty member to hold up to two sections of
# the same course in a term (the service caps it at two).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0030_pending_registration_student_type"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="teachingassignment",
            name="unique_teaching_load_per_course",
        ),
        migrations.AddConstraint(
            model_name="teachingassignment",
            constraint=models.UniqueConstraint(
                fields=("professor", "subject", "term", "program_section"),
                name="unique_teaching_load_per_course_section",
            ),
        ),
    ]

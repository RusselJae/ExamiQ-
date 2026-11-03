"""Backfill is_irregular and academic_year for existing students.

All existing students are assumed REGULAR (bound to a section). Irregular
students are flagged manually by the coordinator after reviewing the roster.
"""

from django.core.management.base import BaseCommand

from apps.users.models import User


class Command(BaseCommand):
    help = "Backfill is_irregular=False and academic_year for existing students."

    def handle(self, *args, **kwargs):
        students = User.objects.filter(role=User.Role.STUDENT)
        updated = 0
        for u in students:
            if u.section_id and u.year_level_id:
                u.is_irregular = False
                u.academic_year = u.year_level
                u.save(update_fields=["is_irregular", "academic_year"])
                updated += 1
                self.stdout.write(f"Regular: {u.student_number}")
            else:
                u.is_irregular = True
                u.academic_year = u.year_level
                u.save(update_fields=["is_irregular", "academic_year"])
                updated += 1
                self.stdout.write(f"Irregular: {u.student_number}")

        self.stdout.write(self.style.SUCCESS(f"Backfilled {updated} student(s)."))

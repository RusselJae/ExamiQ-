"""Backfill one TeachingAssignment per handled course for the current term.

Faculty who picked subjects on their profile predate the chairperson
assignment workflow, so the coordinator Faculty Courses page shows 0 faculty
for them even though their dashboard lists handled courses. This command
materializes one TeachingAssignment per (professor, subject, term) pair and
collapses any legacy multi-section duplicates down to a single row.
Idempotent: existing assignments are skipped.
"""

from django.core.management.base import BaseCommand

from apps.users.models import AcademicTerm, AcademicYear, User


class Command(BaseCommand):
    help = (
        "Create one TeachingAssignment per handled course for the current "
        "term, collapsing legacy multi-section duplicates."
    )

    def handle(self, *args, **options):
        from apps.users.assignment_services import create_teaching_assignment
        from apps.users.models import ProgramSection, TeachingAssignment

        year = AcademicYear.get_current()
        if year is None:
            self.stderr.write("No current academic year; nothing to do.")
            return
        term = AcademicTerm.get_current()
        if term is None:
            self.stderr.write("No current academic term; nothing to do.")
            return

        collapsed_total = 0
        created_total = 0
        skipped_total = 0
        faculty_done = 0
        professors = User.objects.filter(
            role=User.Role.PROFESSOR, is_active=True
        ).prefetch_related("assigned_subjects")
        for professor in professors:
            subjects = list(professor.assigned_subjects.all())
            if not subjects:
                continue
            made_any = False
            for subject in subjects:
                # Collapse legacy duplicates: keep the earliest row.
                dupes = list(
                    TeachingAssignment.objects.filter(
                        professor=professor, subject=subject, term=term
                    ).order_by("pk")
                )
                if len(dupes) > 1:
                    for extra in dupes[1:]:
                        extra.delete()
                    collapsed_total += len(dupes) - 1
                if dupes:
                    skipped_total += 1
                    continue
                section = (
                    ProgramSection.objects.filter(
                        program_id=subject.program_id,
                        year_level_id=subject.year_level_id,
                        is_active=True,
                    )
                    .order_by("label")
                    .first()
                )
                if section is None:
                    skipped_total += 1
                    continue
                try:
                    _, was_created = create_teaching_assignment(
                        professor=professor,
                        program_section=section,
                        subject=subject,
                        term=term,
                        assigned_by=None,
                    )
                except ValueError as exc:
                    self.stderr.write(f"Skipping {subject.code}: {exc}")
                    skipped_total += 1
                    continue
                if was_created:
                    created_total += 1
                    made_any = True
                else:
                    skipped_total += 1
            if made_any:
                faculty_done += 1
        self.stdout.write(
            f"Backfilled {created_total} teaching assignment(s) for "
            f"{faculty_done} facult(y/ies); collapsed {collapsed_total} "
            f"duplicate(s); {skipped_total} skipped."
        )

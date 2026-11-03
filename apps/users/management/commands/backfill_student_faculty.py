"""Backfill StudentFacultyAssignment rows for students missing them."""

from django.core.management.base import BaseCommand

from apps.questions.models import Subject
from apps.users.models import AcademicYear, StudentFacultyAssignment, User


class Command(BaseCommand):
    help = (
        "Assign faculty to students who have none for the current academic "
        "year, based on their subjects and teaching assignments."
    )

    def handle(self, *args, **options):
        from apps.users.faculty_assignment_services import find_faculty_for_subject
        from apps.users.services import get_student_subjects

        year = AcademicYear.get_current()
        if year is None:
            self.stderr.write("No current academic year; nothing to do.")
            return

        assigned_ids = set(
            StudentFacultyAssignment.objects.filter(academic_year=year).values_list(
                "student_id", flat=True
            )
        )
        students = (
            User.objects.filter(role=User.Role.STUDENT, is_archived=False)
            .exclude(pk__in=assigned_ids)
            .select_related("section", "year_level")
        )
        created = 0
        skipped = 0
        for student in students.iterator():
            if student.is_irregular:
                subjects = list(get_student_subjects(student, term_id=None))
            elif student.year_level_id:
                subjects = list(
                    Subject.objects.filter(
                        program__slug=User.HomeDegreeProgram.BSED_MATH,
                        year_level_id=student.year_level_id,
                    )
                )
            else:
                skipped += 1
                continue
            made_any = False
            for subject in subjects:
                faculty = find_faculty_for_subject(student, subject, year)
                if faculty is None:
                    continue
                _, was_created = StudentFacultyAssignment.objects.get_or_create(
                    student=student,
                    faculty=faculty,
                    subject=subject,
                    academic_year=year,
                )
                made_any = made_any or was_created
            if made_any:
                created += 1
            else:
                skipped += 1
        self.stdout.write(
            f"Assigned faculty for {created} student(s); "
            f"{skipped} skipped (no subjects or no teaching assignment)."
        )

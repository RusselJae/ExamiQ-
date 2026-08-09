"""Hard-delete subjects/questions/courses outside current BSED Math subjects."""

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.questions.models import Question, Subject, Topic
from apps.users.models import Course, Program, User


class Command(BaseCommand):
    help = (
        "Delete subjects, topics, questions, and courses that are not under "
        "the current BSED Math program subjects."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        bsed = Program.objects.filter(slug=User.HomeDegreeProgram.BSED_MATH).first()
        if not bsed:
            self.stderr.write("BSED Math program not found; nothing to clean.")
            return

        keep_subject_ids = set(
            Subject.objects.filter(program=bsed).values_list("pk", flat=True)
        )
        keep_codes = set(
            Subject.objects.filter(program=bsed).values_list("code", flat=True)
        )

        orphan_subjects = Subject.objects.exclude(program=bsed)
        orphan_topics = Topic.objects.exclude(subject_id__in=keep_subject_ids)
        orphan_questions = Question.objects.exclude(
            topic__subject_id__in=keep_subject_ids
        )
        orphan_courses = Course.objects.filter(
            Q(program__isnull=True)
            | ~Q(program=bsed)
            | ~Q(code__in=keep_codes)
        )

        counts = {
            "subjects": orphan_subjects.count(),
            "topics": orphan_topics.count(),
            "questions": orphan_questions.count(),
            "courses": orphan_courses.count(),
        }
        self.stdout.write(
            f"Orphans: {counts['subjects']} subjects, {counts['topics']} topics, "
            f"{counts['questions']} questions, {counts['courses']} courses"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no deletes performed."))
            return

        # Questions first (FK to topics), then topics, subjects, courses.
        deleted_q, _ = orphan_questions.delete()
        deleted_t, _ = orphan_topics.delete()
        deleted_s, _ = orphan_subjects.delete()
        deleted_c, _ = orphan_courses.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted: questions={deleted_q}, topics={deleted_t}, "
                f"subjects={deleted_s}, courses={deleted_c}"
            )
        )

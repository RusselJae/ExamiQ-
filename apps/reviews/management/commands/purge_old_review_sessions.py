"""Delete review/exam sessions older than one month."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.reviews.models import ReviewSession

DEFAULT_DAYS = 30


class Command(BaseCommand):
    help = (
        "Hard-delete ReviewSession rows (and related answers via CASCADE) "
        f"older than {DEFAULT_DAYS} days."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_DAYS,
            help=f"Retention window in days (default: {DEFAULT_DAYS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count matching sessions without deleting.",
        )

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        dry_run = bool(options["dry_run"])
        cutoff = timezone.now() - timedelta(days=days)

        # Prefer ended_at when set; otherwise started_at / created.
        qs = ReviewSession.objects.filter(
            Q(ended_at__lt=cutoff)
            | (Q(ended_at__isnull=True) & Q(started_at__lt=cutoff))
            | (Q(ended_at__isnull=True) & Q(started_at__isnull=True) & Q(created__lt=cutoff))
        )
        count = qs.count()
        if dry_run:
            self.stdout.write(
                f"Would delete {count} review session(s) older than {days} day(s) "
                f"(before {cutoff.isoformat()})."
            )
            return

        deleted, _details = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} review session(s) "
                f"({deleted} DB row(s) including related objects)."
            )
        )

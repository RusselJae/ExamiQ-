"""Remove abandoned signup accounts that never finished email OTP."""

from datetime import timedelta

from django.core.management.base import BaseCommand

from apps.users.otp_services import (
    ABANDONED_SIGNUP_RETENTION,
    cleanup_abandoned_signups,
)


class Command(BaseCommand):
    help = (
        "Delete inactive users who never verified their signup email OTP "
        f"(default retention: {int(ABANDONED_SIGNUP_RETENTION.total_seconds() // 3600)}h), "
        "and drop stale non-primary unverified email addresses. "
        "Schedule via cron in production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting.",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="Override retention window in hours (default 24).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum abandoned users to delete in one run.",
        )

    def handle(self, *args, **options):
        older_than = None
        if options["hours"] is not None:
            older_than = timedelta(hours=max(1, options["hours"]))
        result = cleanup_abandoned_signups(
            older_than=older_than,
            limit=max(1, options["limit"]),
            dry_run=options["dry_run"],
        )
        verb = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(
            f"{verb} {result['users']} abandoned signup user(s) "
            f"and ~{result['emails']} unverified email row(s)."
        )

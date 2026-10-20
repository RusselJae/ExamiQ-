"""Abandoned signup / unverified email cleanup."""

from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.utils import timezone

from apps.users.models import User
from apps.users.otp_services import cleanup_abandoned_signups


@pytest.mark.django_db
class TestCleanupAbandonedSignups:
    def test_removes_stale_inactive_unverified_user(self, db):
        stale = User.objects.create_user(
            email="stale-signup@test.edu",
            password="strongpass123!",
            role=User.Role.STUDENT,
            is_active=False,
            approval_status=User.ApprovalStatus.APPROVED,
        )
        User.objects.filter(pk=stale.pk).update(
            date_joined=timezone.now() - timedelta(hours=25)
        )
        EmailAddress.objects.create(
            user=stale,
            email=stale.email,
            verified=False,
            primary=True,
        )

        result = cleanup_abandoned_signups(older_than=timedelta(hours=24))
        assert result["users"] == 1
        assert not User.objects.filter(email="stale-signup@test.edu").exists()

    def test_keeps_verified_inactive_pending_faculty(self, department):
        pending = User.objects.create_user(
            email="pending-faculty@test.edu",
            password="strongpass123!",
            role=User.Role.PROFESSOR,
            department=department,
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        User.objects.filter(pk=pending.pk).update(
            date_joined=timezone.now() - timedelta(days=3)
        )
        EmailAddress.objects.create(
            user=pending,
            email=pending.email,
            verified=True,
            primary=True,
        )

        result = cleanup_abandoned_signups(older_than=timedelta(hours=24))
        assert result["users"] == 0
        assert User.objects.filter(email="pending-faculty@test.edu").exists()

    def test_keeps_active_users(self, student):
        User.objects.filter(pk=student.pk).update(
            date_joined=timezone.now() - timedelta(days=30)
        )
        result = cleanup_abandoned_signups(older_than=timedelta(hours=24))
        assert result["users"] == 0
        assert User.objects.filter(pk=student.pk).exists()

    def test_dry_run_does_not_delete(self, db):
        stale = User.objects.create_user(
            email="dry-run@test.edu",
            password="strongpass123!",
            role=User.Role.STUDENT,
            is_active=False,
        )
        User.objects.filter(pk=stale.pk).update(
            date_joined=timezone.now() - timedelta(hours=30)
        )
        result = cleanup_abandoned_signups(
            older_than=timedelta(hours=24), dry_run=True
        )
        assert result["users"] == 1
        assert User.objects.filter(email="dry-run@test.edu").exists()

    def test_management_command(self, db):
        stale = User.objects.create_user(
            email="cmd-cleanup@test.edu",
            password="strongpass123!",
            role=User.Role.STUDENT,
            is_active=False,
        )
        User.objects.filter(pk=stale.pk).update(
            date_joined=timezone.now() - timedelta(hours=30)
        )
        call_command("cleanup_unverified_signups", hours=24)
        assert not User.objects.filter(email="cmd-cleanup@test.edu").exists()

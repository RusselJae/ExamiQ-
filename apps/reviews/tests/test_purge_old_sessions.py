"""Tests for purge_old_review_sessions management command."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.reviews.models import ReviewSession


@pytest.mark.django_db
def test_purge_old_review_sessions_deletes_stale(student, topic, capsys):
    old = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty="easy",
        status=ReviewSession.Status.COMPLETED,
    )
    recent = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty="easy",
        status=ReviewSession.Status.COMPLETED,
    )
    ReviewSession.objects.filter(pk=old.pk).update(
        started_at=timezone.now() - timedelta(days=45),
        ended_at=timezone.now() - timedelta(days=45),
        created=timezone.now() - timedelta(days=45),
    )

    call_command("purge_old_review_sessions", days=30)
    assert not ReviewSession.objects.filter(pk=old.pk).exists()
    assert ReviewSession.objects.filter(pk=recent.pk).exists()


@pytest.mark.django_db
def test_purge_old_review_sessions_dry_run(student, topic):
    old = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty="easy",
        status=ReviewSession.Status.COMPLETED,
    )
    ReviewSession.objects.filter(pk=old.pk).update(
        started_at=timezone.now() - timedelta(days=40),
        ended_at=timezone.now() - timedelta(days=40),
    )
    call_command("purge_old_review_sessions", days=30, dry_run=True)
    assert ReviewSession.objects.filter(pk=old.pk).exists()

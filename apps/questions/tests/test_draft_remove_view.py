"""Tests for draft stem removal and soft-delete generation exclusions."""

import json

import pytest
from django.urls import reverse

from apps.questions.models import ExcludedQuestion
from apps.questions.services import exclusion_set_for_topic, stem_fingerprint
from apps.users.models import User


@pytest.fixture
def course_with_subject(course, subject):
    """Align subject code with course code so _subject_for_course finds it."""
    subject.code = course.code
    subject.save(update_fields=["code"])
    return course


@pytest.fixture
def other_professor(db, department):
    return User.objects.create_user(
        email="other-prof@test.edu",
        password="testpass123",
        role=User.Role.PROFESSOR,
        department=department,
    )


@pytest.mark.django_db
class TestQuestionDraftRemoveView:
    def _post(self, client, professor, course_with_subject, topic, **payload):
        client.force_login(professor)
        url = reverse(
            "analytics_professor:question_draft_delete",
            kwargs={"course_pk": course_with_subject.pk},
        )
        return client.post(url, payload)

    def test_delete_selected_stems_creates_exclusions(
        self, client, professor, course_with_subject, topic
    ):
        response = self._post(
            client,
            professor,
            course_with_subject,
            topic,
            topic_id=str(topic.pk),
            stems_json=json.dumps(["Stem one.", "Stem two."]),
        )
        assert response.status_code == 200
        keys = exclusion_set_for_topic(topic.pk)
        assert stem_fingerprint(topic.pk, "Stem one.") in keys
        assert stem_fingerprint(topic.pk, "Stem two.") in keys
        assert response.json() == {
            "topic_id": topic.pk,
            "excluded": 2,
        }
        rows = list(
            ExcludedQuestion.objects.filter(topic=topic).values_list(
                "reason", flat=True
            )
        )
        assert rows == [ExcludedQuestion.Reason.DRAFT_REMOVED] * 2
        assert all(
            row.excluded_by_id == professor.pk
            for row in ExcludedQuestion.objects.filter(topic=topic)
        )

    def test_empty_stems_are_ignored(
        self, client, professor, course_with_subject, topic
    ):
        response = self._post(
            client,
            professor,
            course_with_subject,
            topic,
            topic_id=str(topic.pk),
            stems_json=json.dumps(["   ", "Valid stem."]),
        )
        assert response.status_code == 200
        assert response.json()["excluded"] == 1
        keys = exclusion_set_for_topic(topic.pk)
        assert len(keys) == 1

    def test_reposting_same_stems_is_idempotent(
        self, client, professor, course_with_subject, topic
    ):
        payload = {
            "topic_id": str(topic.pk),
            "stems_json": json.dumps(["Repeated stem."]),
        }
        first = self._post(client, professor, course_with_subject, topic, **payload)
        second = self._post(client, professor, course_with_subject, topic, **payload)
        assert first.json()["excluded"] == 1
        assert second.json()["excluded"] == 0
        assert ExcludedQuestion.objects.filter(topic=topic).count() == 1

    def test_requires_professor_who_owns_the_course(
        self, client, other_professor, course_with_subject, topic
    ):
        client.force_login(other_professor)
        url = reverse(
            "analytics_professor:question_draft_delete",
            kwargs={"course_pk": course_with_subject.pk},
        )
        response = client.post(
            url, {"topic_id": str(topic.pk), "stems_json": json.dumps(["x"])}
        )
        assert response.status_code == 404
        assert ExcludedQuestion.objects.count() == 0

    def test_unauthenticated_gives_404(
        self, client, course_with_subject, topic
    ):
        # ProfessorCourseMixin.dispatch runs before the login redirect and
        # raises Http404 when the requester cannot access the course.
        url = reverse(
            "analytics_professor:question_draft_delete",
            kwargs={"course_pk": course_with_subject.pk},
        )
        response = client.post(
            url, {"topic_id": str(topic.pk), "stems_json": json.dumps(["x"])}
        )
        assert response.status_code == 404

    def test_invalid_payload_returns_400(
        self, client, professor, course_with_subject, topic
    ):
        response = self._post(
            client,
            professor,
            course_with_subject,
            topic,
            topic_id=str(topic.pk),
            stems_json="not json",
        )
        assert response.status_code == 400
        assert ExcludedQuestion.objects.count() == 0

    def test_topic_from_another_subject_returns_404(
        self, client, professor, course_with_subject, topic
    ):
        from apps.questions.models import Subject, Topic

        other_subject = Subject.objects.create(
            program=course_with_subject.program,
            code="OTHER-1",
            year_level=topic.subject.year_level,
            semester=1,
            name="Other subject",
        )
        other_topic = Topic.objects.create(subject=other_subject, name="Other topic")
        response = self._post(
            client,
            professor,
            course_with_subject,
            topic,
            topic_id=str(other_topic.pk),
            stems_json=json.dumps(["x"]),
        )
        assert response.status_code == 404
        assert ExcludedQuestion.objects.count() == 0


@pytest.mark.django_db
class TestQuestionDeleteExcludesStem:
    def test_soft_delete_records_exclusion(
        self, client, professor, course, mcq_question
    ):
        question, _choice = mcq_question
        # Client-side delete flows target the analytics_professor namespace.
        client.force_login(professor)
        url = reverse(
            "analytics_professor:question_delete",
            kwargs={"course_pk": course.pk, "question_pk": question.pk},
        )
        response = client.post(url)
        assert response.status_code == 302

        question.refresh_from_db()
        assert question.is_active is False
        keys = exclusion_set_for_topic(question.topic_id)
        assert stem_fingerprint(question.topic_id, question.stem) in keys
        exclusion = ExcludedQuestion.objects.get(topic=question.topic)
        assert exclusion.reason == ExcludedQuestion.Reason.DELETED
        assert exclusion.excluded_by_id == professor.pk

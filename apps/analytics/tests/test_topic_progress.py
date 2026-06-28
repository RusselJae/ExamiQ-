import pytest
from django.urls import reverse

from apps.analytics.services import topic_progress_summary
from apps.questions.models import Question
from apps.reviews.services import start_review_session, submit_answer


@pytest.mark.django_db
class TestTopicProgressSummary:
    def test_includes_topic_and_subject_ids(self, student, topic, mcq_question):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        submit_answer(
            session=session,
            question=question,
            confidence=3,
            selected_choice=correct,
            time_spent_seconds=5,
        )

        rows = topic_progress_summary(student)
        assert len(rows) == 1
        assert rows[0]["topic_id"] == topic.pk
        assert rows[0]["subject_id"] == topic.subject_id
        assert rows[0]["topic_name"] == topic.name


@pytest.mark.django_db
class TestTopicProgressPage:
    def test_topic_progress_includes_review_setup_link(self, client, student, topic, mcq_question):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        submit_answer(
            session=session,
            question=question,
            confidence=3,
            selected_choice=correct,
            time_spent_seconds=5,
        )

        client.force_login(student)
        response = client.get(reverse("analytics_student:topic_progress"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "Review topic" in content
        assert f"{reverse('reviews:setup')}?topic={topic.pk}" in content

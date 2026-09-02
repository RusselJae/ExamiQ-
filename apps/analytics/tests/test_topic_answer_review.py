import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.questions.models import Question
from apps.reviews.services import start_review_session, submit_answer

User = get_user_model()


@pytest.mark.django_db
class TestFacultyRoleLabel:
    def test_professor_role_displays_as_faculty(self, professor):
        assert professor.get_role_display() == "Faculty"


@pytest.mark.django_db
class TestTopicAnswerReview:
    def test_non_student_gets_forbidden(self, client, professor, topic):
        client.force_login(professor)
        response = client.get(
            reverse("analytics_student:topic_answer_review", kwargs={"topic_id": topic.pk})
        )
        assert response.status_code == 403

    def test_student_redirects_to_mistakes(self, client, student, topic):
        client.force_login(student)
        response = client.get(
            reverse("analytics_student:topic_answer_review", kwargs={"topic_id": topic.pk})
        )
        assert response.status_code == 302
        assert response.url == reverse("analytics_student:mistakes")

    def test_student_with_answers_redirects_to_mistakes(
        self, client, student, topic, mcq_question
    ):
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
        response = client.get(
            reverse("analytics_student:topic_answer_review", kwargs={"topic_id": topic.pk})
        )
        assert response.status_code == 302
        assert response.url == reverse("analytics_student:mistakes")

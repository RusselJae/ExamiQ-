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

    def test_student_without_answers_gets_404(self, client, student, topic):
        client.force_login(student)
        response = client.get(
            reverse("analytics_student:topic_answer_review", kwargs={"topic_id": topic.pk})
        )
        assert response.status_code == 404

    def test_student_sees_answer_history(self, client, student, topic, mcq_question):
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
        assert response.status_code == 200
        content = response.content.decode()
        assert question.stem[:20] in content or question.stem in content
        assert "Correct" in content

    def test_wrong_answer_shows_feedback_and_solution(self, client, student, topic, mcq_question):
        from apps.analytics.models import MistakeRecord
        from apps.questions.models import ExplanationStep

        question, correct = mcq_question
        ExplanationStep.objects.create(
            question=question,
            order=1,
            content="Step 1: Add 2 and 2 to get 4.",
        )
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        wrong = question.choices.exclude(is_correct=True).first()
        answer = submit_answer(
            session=session,
            question=question,
            confidence=2,
            selected_choice=wrong,
            time_spent_seconds=5,
        )
        MistakeRecord.objects.filter(answer=answer).update(
            ai_feedback="You picked a distractor — remember to add carefully."
        )

        client.force_login(student)
        response = client.get(
            reverse("analytics_student:topic_answer_review", kwargs={"topic_id": topic.pk})
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "Why you missed it" in content
        assert "distractor" in content
        assert "Step-by-step solution" in content
        assert "Add 2 and 2" in content
        assert "Back to mistake log" in content

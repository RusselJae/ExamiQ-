import pytest
from django.urls import reverse

from apps.analytics.services import generate_mistake_feedback
from apps.questions.models import ExplanationStep, Question
from apps.reviews.services import start_review_session, submit_answer


@pytest.mark.django_db
class TestAnswerDetailAndMistakeLog:
    def test_mistake_log_has_view_link(self, client, student, topic, mcq_question):
        question, _ = mcq_question
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

        client.force_login(student)
        response = client.get(reverse("analytics_student:mistakes"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "View" in content
        assert "open-tutor-btn" in content
        assert f'data-answer-id="{answer.pk}"' in content

    def test_weak_areas_redirects_to_mistakes(self, client, student, topic, mcq_question):
        question, _ = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        wrong = question.choices.exclude(is_correct=True).first()
        submit_answer(
            session=session,
            question=question,
            confidence=2,
            selected_choice=wrong,
            time_spent_seconds=5,
        )

        client.force_login(student)
        response = client.get(reverse("analytics_student:mistake_patterns"))
        assert response.status_code == 302
        assert response.url == reverse("analytics_student:mistakes")

    def test_answer_detail_shows_feedback_after_generate(self, client, student, topic, mcq_question):
        question, _ = mcq_question
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

        client.force_login(student)
        detail_url = reverse("analytics_student:answer_detail", kwargs={"answer_pk": answer.pk})
        response = client.get(detail_url)
        content = response.content.decode()
        assert response.status_code == 200
        assert "Generate feedback" in content
        assert "Back to mistake log" in content

        generate_url = reverse(
            "analytics_student:generate_answer_feedback",
            kwargs={"answer_pk": answer.pk},
        )
        gen_response = client.post(generate_url)
        assert gen_response.status_code == 200
        assert "Why you missed it" in gen_response.content.decode()

        answer.mistake_record.refresh_from_db()
        assert answer.mistake_record.ai_feedback

        response = client.get(detail_url)
        assert "Why you missed it" in response.content.decode()
        assert "Generate feedback" not in response.content.decode()


@pytest.mark.django_db
def test_rule_based_feedback_for_true_false(topic):
    from apps.analytics.services import _rule_based_answer_feedback
    from apps.questions.models import Question
    from apps.reviews.models import Answer, ReviewSession
    from apps.users.models import User

    question = Question.objects.create(
        topic=topic,
        stem="Pi is exactly 3.",
        question_type=Question.QuestionType.TRUE_FALSE,
        expected_answer="False",
        difficulty=Question.Difficulty.EASY,
    )
    student = User.objects.create_user(
        email="tf-student@test.edu",
        password="x",
        role=User.Role.STUDENT,
    )
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        status=ReviewSession.Status.COMPLETED,
    )
    answer = Answer.objects.create(
        session=session,
        question=question,
        numeric_response="True",
        confidence=3,
        is_correct=False,
    )
    feedback = _rule_based_answer_feedback(answer)
    assert "False" in feedback
    assert "True" in feedback

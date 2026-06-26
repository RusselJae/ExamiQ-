import pytest
from django.urls import reverse

from apps.questions.models import Question, QuestionChoice
from apps.reviews.models import ReviewSession
from apps.reviews.services import start_review_session


@pytest.mark.django_db
class TestQuestionPartialView:
    def test_htmx_redirect_when_no_questions(self, client, student, topic):
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            status=ReviewSession.Status.ACTIVE,
            planned_question_count=0,
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 204
        assert response["HX-Redirect"] == reverse("reviews:summary", kwargs={"pk": session.pk})
        session.refresh_from_db()
        assert session.status == ReviewSession.Status.COMPLETED

    def test_renders_question_when_available(self, client, student, topic, mcq_question):
        question, _ = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert question.stem in content
        assert "confidence-slider" in content


@pytest.mark.django_db
class TestReviewSessionFocusUI:
    def test_session_page_includes_progress_bar_and_slider_context(self, client, student, topic, mcq_question):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        client.force_login(student)
        response = client.get(reverse("reviews:session", kwargs={"pk": session.pk}))
        content = response.content.decode()
        assert response.status_code == 200
        assert "focus-header" in content
        assert "focus-progress-bar" in content
        assert "focus-question-dots" in content
        assert "session-status" in content


@pytest.mark.django_db
class TestSubmitAnswerView:
    def test_timed_exam_records_confidence(self, client, student, topic, mcq_question):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        client.force_login(student)
        url = reverse("reviews:submit_answer", kwargs={"pk": session.pk, "question_id": question.pk})
        response = client.post(
            url,
            {
                "selected_choice": correct.pk,
                "confidence": "4",
                "time_spent_seconds": "12",
                "timed_out": "false",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        answer = session.answers.get()
        assert answer.confidence == 4

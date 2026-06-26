from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.ai.exceptions import AIServiceUnavailableError


@pytest.mark.django_db
class TestQuestionAIGenerateView:
    @patch("apps.questions.views_professor.get_question_generator")
    def test_shows_ai_error_in_modal(self, mock_get_generator, client, professor, course, topic):
        generator = mock_get_generator.return_value
        generator.generate.side_effect = AIServiceUnavailableError(
            "AI unavailable: API quota exceeded."
        )
        client.force_login(professor)
        url = reverse("analytics_professor:question_ai_generate", kwargs={"course_pk": course.pk})
        response = client.post(
            url,
            {"topic": topic.pk, "difficulty": "easy"},
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "AI unavailable: API quota exceeded." in content

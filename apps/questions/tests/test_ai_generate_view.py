from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.models import AIGenerationJob


def _run_thread_inline(target, args=(), kwargs=None, **_ignored):
    """Execute job work synchronously instead of in a background thread."""
    kwargs = kwargs or {}
    target(*args, **kwargs)
    return MagicMock()


def _sample_module_file():
    content = (
        b"Module 1: Linear Equations\n"
        b"Solve for x in equations of the form ax + b = c.\n"
        b"Example: 2x + 3 = 11 implies x = 4.\n"
        b"Practice applying inverse operations carefully."
    )
    return SimpleUploadedFile("module.txt", content, content_type="text/plain")


@pytest.mark.django_db(transaction=True)
class TestQuestionAIGenerateView:
    @patch("apps.ai.job_services.threading.Thread", side_effect=_run_thread_inline)
    @patch("apps.ai.job_services.get_question_generator")
    def test_enqueues_job_and_surfaces_ai_error(
        self, mock_get_generator, _mock_thread, client, professor, course, topic
    ):
        generator = mock_get_generator.return_value
        generator.generate.side_effect = AIServiceUnavailableError(
            "AI unavailable: API quota exceeded."
        )
        client.force_login(professor)
        url = reverse("analytics_professor:question_ai_generate", kwargs={"course_pk": course.pk})
        response = client.post(
            url,
            {"topic": topic.pk, "difficulty": "easy", "source_file": _sample_module_file()},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["job_id"]
        assert data["status_url"]

        job = AIGenerationJob.objects.get(pk=data["job_id"])
        assert job.status == AIGenerationJob.Status.FAILED

        status_url = reverse(
            "analytics_professor:question_ai_generate_status",
            kwargs={"course_pk": course.pk, "job_id": job.pk},
        )
        status_response = client.get(status_url, HTTP_ACCEPT="text/html")
        assert status_response.status_code == 200
        content = status_response.content.decode()
        assert "AI unavailable: API quota exceeded." in content

    def test_requires_source_file(self, client, professor, course, topic):
        client.force_login(professor)
        url = reverse("analytics_professor:question_ai_generate", kwargs={"course_pk": course.pk})
        response = client.post(url, {"topic": topic.pk, "difficulty": "easy"})
        assert response.status_code == 400
        assert "Upload" in response.json()["error"]

    @patch("apps.ai.job_services.threading.Thread", side_effect=_run_thread_inline)
    @patch("apps.ai.job_services.get_question_generator")
    def test_status_returns_modal_on_success(
        self, mock_get_generator, _mock_thread, client, professor, course, topic
    ):
        generator = mock_get_generator.return_value
        generator.generate.return_value = [
            {
                "stem": "What is 2+2?",
                "choices": [
                    {"label": "A", "text": "4", "is_correct": True},
                    {"label": "B", "text": "3", "is_correct": False},
                    {"label": "C", "text": "5", "is_correct": False},
                    {"label": "D", "text": "0", "is_correct": False},
                ],
                "correct_label": "A",
                "concept_tag": "Addition",
                "explanation_steps": ["Add the numbers."],
            }
        ]
        client.force_login(professor)
        start_url = reverse(
            "analytics_professor:question_ai_generate", kwargs={"course_pk": course.pk}
        )
        response = client.post(
            start_url,
            {
                "topic": topic.pk,
                "difficulty": "easy",
                "count": "1",
                "source_file": _sample_module_file(),
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        job = AIGenerationJob.objects.get(pk=job_id)
        assert job.status == AIGenerationJob.Status.SUCCEEDED
        assert "Linear Equations" in job.source_material

        status_url = reverse(
            "analytics_professor:question_ai_generate_status",
            kwargs={"course_pk": course.pk, "job_id": job_id},
        )
        status_response = client.get(status_url, HTTP_ACCEPT="text/html")
        assert status_response.status_code == 200
        assert "What is 2+2?" in status_response.content.decode()

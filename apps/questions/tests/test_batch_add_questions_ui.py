"""Add-questions batch screen: source picker + draft batch actions."""

import re

import pytest
from django.urls import reverse

from apps.ai.models import LearningDocument


@pytest.fixture
def ready_material(course, professor, subject):
    return LearningDocument.objects.create(
        course_id=course.pk,
        subject=subject,
        created_by=professor,
        title="GNED 03_Overview",
        original_name="GNED 03_Overview.txt",
        status=LearningDocument.Status.READY,
    )


@pytest.mark.django_db
class TestBatchAddQuestionsScreen:
    def url(self, course):
        return reverse(
            "analytics_professor:question_create",
            kwargs={"course_pk": course.pk},
        )

    def test_source_material_picker_lists_saved_and_upload(
        self, client, professor, course, ready_material
    ):
        client.force_login(professor)
        response = client.get(self.url(course))
        content = response.content.decode()

        assert response.status_code == 200
        # One picker holds both saved modules and the upload affordance.
        assert 'id="ai-library-document"' in content
        assert "GNED 03_Overview" in content
        assert "data-source-upload-option" in content
        assert "data-source-upload-group" in content
        assert 'data-dropzone-input="ai-source-file"' in content

    def test_difficulty_offers_ai_decides_without_mix_wording(
        self, client, professor, course
    ):
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()

        assert "data-difficulty-auto" in content
        assert "AI decides" in content
        # The old "(pick 1-3)" hint is gone.
        assert "pick 1" not in content
        assert "Difficulty mix" not in content
        # Band pills are still there next to the new control.
        assert 'id="settings-difficulty"' in content
        assert 'data-pill-max="3"' in content

    def test_no_difficulty_is_selected_by_default(self, client, professor, course):
        """Switching courses must not pre-fill a difficulty band."""
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()

        assert 'value="medium" selected' not in content
        assert 'class="batch-pill is-selected"' not in content
        # Helper copy under the difficulty pills was removed; toast still exists.
        markup = re.sub(r"<script\b.*?</script>", "", content, flags=re.DOTALL)
        assert "Select at least one difficulty before generating." not in markup

    def test_ai_decides_maps_to_all_three_bands(self):
        """Selecting every band is what "AI decides" submits."""
        from apps.ai.job_services import parse_job_difficulties, split_counts_across

        difficulties = parse_job_difficulties("easy,medium,hard")
        assert len(difficulties) == 3
        assert sum(split_counts_across(6, len(difficulties))) == 6

    def test_setup_card_has_no_filler_copy(self, client, professor, course):
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()
        # JS guards still raise the same wording as a toast; only assert on
        # what is actually rendered above the fold.
        markup = re.sub(r"<script\b.*?</script>", "", content, flags=re.DOTALL)

        for removed in (
            "Set up this batch",
            "These settings apply to everything you generate or add below.",
            "Pick a saved module, or upload a new file",
            "Questions you add are saved under the selected subject.",
            "Select a course subject to save questions.",
        ):
            assert removed not in markup

    def test_batch_actions_include_validate_and_delete_selected(
        self, client, professor, course
    ):
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()

        assert 'id="validate-all-btn"' in content
        assert "Validate selected" in content
        assert 'id="delete-selected-btn"' in content
        assert "Delete selected" in content
        assert 'id="publish-validated-count"' in content
        assert "Publish validated (0)" in content
        assert "data-select-all" in content

    def test_batch_table_is_scrollable_without_per_row_controls(
        self, client, professor, course
    ):
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()

        # Table lives inside a fixed-height scroll region.
        assert 'id="questions-table-scroll"' in content
        assert "batch-table-scroll" in content
        # Per-row validate/delete controls are gone; Edit rides with the choices.
        assert "delete-question-btn" not in content
        assert "batch-row-actions" not in content

    def test_generated_review_modal_marks_fits(self, client, professor, course, topic):
        from apps.ai.models import AIGenerationJob

        job = AIGenerationJob.objects.create(
            job_type=AIGenerationJob.JobType.QUESTION_GENERATE,
            created_by=professor,
            course_id=course.pk,
            topic_id=topic.pk,
            difficulty="medium",
            count=1,
            question_type="mcq",
            status=AIGenerationJob.Status.SUCCEEDED,
            result={
                "variations": [
                    {
                        "stem": "What is 2+2?",
                        "concept_tag": "Addition",
                        "difficulty": "easy",
                        "question_type": "mcq",
                        "correct_label": "A",
                        "explanation_steps": ["Add them."],
                        "choices": [
                            {"label": "A", "text": "4", "is_correct": True},
                            {"label": "B", "text": "3", "is_correct": False},
                            {"label": "C", "text": "5", "is_correct": False},
                            {"label": "D", "text": "0", "is_correct": False},
                        ],
                    }
                ]
            },
        )
        client.force_login(professor)
        status_url = reverse(
            "analytics_professor:question_ai_generate_status",
            kwargs={"course_pk": course.pk, "job_id": job.pk},
        )
        response = client.get(status_url, HTTP_ACCEPT="text/html")
        content = response.content.decode()

        assert response.status_code == 200
        assert "Review generated questions" in content
        assert "gen-card" in content
        assert "Rounds on Beginner" in content
        assert "1 step, no reasoning" in content
        assert "Regenerate harder" in content
        assert "Added questions stay as drafts until validated." in content
        assert "selected to batch" in content

    def test_generate_returns_uploaded_material_id(
        self, client, professor, course, subject, topic
    ):
        from unittest.mock import MagicMock, patch

        from django.core.files.uploadedfile import SimpleUploadedFile

        subject.code = course.code
        subject.save(update_fields=["code"])

        def _run_thread_inline(target, args=(), kwargs=None, **_ignored):
            kwargs = kwargs or {}
            target(*args, **kwargs)
            return MagicMock()

        generator = MagicMock()
        generator.generate.return_value = []

        with (
            patch(
                "apps.ai.job_services.threading.Thread",
                side_effect=_run_thread_inline,
            ),
            patch(
                "apps.ai.job_services.get_question_generator", return_value=generator
            ),
            patch(
                "apps.ai.subject_relevance.assess_subject_relevance",
                return_value={
                    "related": True,
                    "matched_topic_id": topic.pk,
                    "subject_score": 1,
                    "topic_score": 1,
                    "reason": "",
                },
            ),
        ):
            client.force_login(professor)
            response = client.post(
                reverse(
                    "analytics_professor:question_ai_generate",
                    kwargs={"course_pk": course.pk},
                ),
                {
                    "topic": topic.pk,
                    "difficulty": "medium",
                    "count": "1",
                    "source_file": SimpleUploadedFile(
                        "module.txt",
                        (
                            b"Test Subject - Algebra: Linear Equations\n"
                            b"Solve for x in equations of the form ax + b = c.\n"
                            b"Example: 2x + 3 = 11 implies x = 4.\n"
                            b"Practice applying inverse operations carefully."
                        ),
                        content_type="text/plain",
                    ),
                },
            )

        assert response.status_code == 202, response.content.decode()[:400]
        data = response.json()
        assert data["learning_document_id"]
        assert data["learning_document_title"]
        assert LearningDocument.objects.filter(pk=data["learning_document_id"]).exists()

"""Add-questions batch screen: source picker + draft batch actions."""

import json
import re

import pytest
from django.urls import reverse

from apps.ai.models import LearningDocument
from apps.questions.models import Question
from apps.users.models import Course


def _json_script(content: str, element_id: str):
    match = re.search(
        rf'<script id="{element_id}" type="application/json">(.*?)</script>',
        content,
        re.DOTALL,
    )
    assert match, f"{element_id} JSON script missing"
    return json.loads(match.group(1))


@pytest.fixture
def ready_material(course, professor, subject):
    return LearningDocument.objects.create(
        course_id=course.pk,
        subject=subject,
        created_by=professor,
        title="GNED 03_Overview",
        original_name="GNED 03_Overview.pdf",
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
        assert "Questions per difficulty" in content

    def test_no_difficulty_is_selected_by_default(self, client, professor, course):
        """Switching courses must not pre-fill a difficulty band."""
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()

        assert 'value="medium" selected' not in content
        assert 'class="batch-pill is-selected"' not in content
        # Helper copy under the difficulty pills was removed; toast still exists.
        markup = re.sub(r"<script\b.*?</script>", "", content, flags=re.DOTALL)
        assert "Select at least one difficulty before generating." not in markup

    def test_difficulty_is_not_required_for_submit(self, client, professor, course):
        """Existing drafts must submit without touching generation settings."""
        client.force_login(professor)
        content = client.get(self.url(course)).content.decode()
        select = re.search(
            r'<select id="settings-difficulty".*?</select>',
            content,
            re.DOTALL,
        )
        assert select
        assert "required" not in select.group(0)

    def test_ai_decides_sends_auto_flag(self):
        """AI decides submits a single "auto" difficulty, not all three bands."""
        from apps.ai.job_services import parse_job_difficulties, split_counts_across

        assert parse_job_difficulties("auto") == ["auto"]
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

    def test_embedded_submit_navigates_top_level_to_question_list(
        self, client, professor, program, subject, topic
    ):
        course = Course.objects.create(
            program=program,
            code=subject.code,
            name="Embed Batch Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.post(
            self.url(course),
            {
                "embed": "1",
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "question_count": 1,
                "stem_0": "What is 3 + 3?",
                "correct_0": "A",
                "concept_tag_0": "Addition",
                "choice_0_A": "6",
                "choice_0_B": "5",
                "choice_0_C": "7",
                "choice_0_D": "8",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "window.top.location.replace" in content
        assert "question bank" in content
        assert Question.objects.filter(stem="What is 3 + 3?").exists()

    def test_saved_drafts_move_from_question_page_to_batch_overlay(
        self, client, professor, course, subject, topic
    ):
        subject.code = course.code
        subject.save(update_fields=["code"])
        draft = Question.objects.create(
            topic=topic,
            stem="Draft that should stay off the question page",
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            status=Question.Status.DRAFT,
        )
        client.force_login(professor)

        content = client.get(
            reverse(
                "analytics_professor:question_list",
                kwargs={"course_pk": course.pk},
            )
        ).content.decode()
        assert "Needs review" not in content
        assert draft.stem not in content
        assert "See 1 draft question" in content
        assert "questions/create/?embed=1" in content

        overlay = client.get(
            self.url(course) + "?embed=1",
        ).content.decode()
        assert "Saved drafts" not in overlay
        assert "submitted-question-stems" in overlay
        batch_data = _json_script(overlay, "draft-batch-data")
        assert [item["draft_id"] for item in batch_data] == [draft.pk]
        assert batch_data[0]["stem"] == draft.stem

        draft.status = Question.Status.APPROVED
        draft.save(update_fields=["status"])
        refreshed = client.get(self.url(course) + "?embed=1").content.decode()
        assert "Saved drafts" not in refreshed
        assert _json_script(refreshed, "draft-batch-data") == []

    def test_saved_draft_submission_updates_instead_of_duplicating(
        self, client, professor, course, subject, topic
    ):
        subject.code = course.code
        subject.save(update_fields=["code"])
        draft = Question.objects.create(
            topic=topic,
            stem="Old draft stem",
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            status=Question.Status.DRAFT,
        )
        client.force_login(professor)
        response = client.post(
            self.url(course),
            {
                "embed": "1",
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "question_count": 1,
                "draft_id_0": draft.pk,
                "topic_id_0": topic.pk,
                "stem_0": "Updated draft stem",
                "correct_0": "A",
                "concept_tag_0": "Updated concept",
                "faculty_attest_0": "1",
                "choice_0_A": "1",
                "choice_0_B": "2",
                "choice_0_C": "3",
                "choice_0_D": "4",
            },
        )

        assert response.status_code == 200
        draft.refresh_from_db()
        assert draft.stem == "Updated draft stem"
        assert draft.status == Question.Status.APPROVED
        assert Question.objects.filter(topic=topic).count() == 1

    def test_saved_draft_submission_can_infer_topic_from_row(
        self, client, professor, course, subject, topic
    ):
        """Submit all should not require the generation setup for saved drafts."""
        subject.code = course.code
        subject.save(update_fields=["code"])
        draft = Question.objects.create(
            topic=topic,
            stem="Draft with its own topic",
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            status=Question.Status.DRAFT,
        )
        client.force_login(professor)
        response = client.post(
            self.url(course),
            {
                "embed": "1",
                "question_count": 1,
                "draft_id_0": draft.pk,
                "topic_id_0": topic.pk,
                "difficulty_0": Question.Difficulty.EASY,
                "stem_0": "Draft submitted from its row topic",
                "correct_0": "A",
                "concept_tag_0": "Row topic concept",
                "choice_0_A": "1",
                "choice_0_B": "2",
                "choice_0_C": "3",
                "choice_0_D": "4",
            },
        )

        assert response.status_code == 200
        draft.refresh_from_db()
        assert draft.stem == "Draft submitted from its row topic"
        assert draft.topic_id == topic.pk
        assert Question.objects.filter(topic=topic).count() == 1

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
            patch(
                "apps.ai.ingest.extract_pages_from_upload",
                return_value=[
                    {
                        "page": 1,
                        "text": (
                            "Test Subject - Algebra: Linear Equations. "
                            "Solve for x in equations of the form ax + b = c."
                        ),
                    }
                ],
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
                        "module.pdf",
                        (
                            b"Test Subject - Algebra: Linear Equations\n"
                            b"Solve for x in equations of the form ax + b = c.\n"
                            b"Example: 2x + 3 = 11 implies x = 4.\n"
                            b"Practice applying inverse operations carefully."
                        ),
                        content_type="application/pdf",
                    ),
                },
            )

        assert response.status_code == 202, response.content.decode()[:400]
        data = response.json()
        assert data["learning_document_id"]
        assert data["learning_document_title"]
        assert LearningDocument.objects.filter(pk=data["learning_document_id"]).exists()

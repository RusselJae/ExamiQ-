"""Tests for materials hub, subject/filename edits, mistake threshold, regenerate."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.ai.models import AIGenerationJob, LearningDocument
from apps.analytics.models import MistakeRecord
from apps.questions.services import (
    distinct_student_mistake_count,
    question_feedback_summary,
    question_needs_revision,
)
from apps.reviews.models import Answer, ReviewSession
from apps.users.assignment_services import get_or_create_catalog_course
from apps.users.models import User


@pytest.mark.django_db
class TestMaterialsHubAndUpload:
    def test_hub_lists_course_and_sidebar_label(
        self, client, professor, subject, bsed_program
    ):
        subject.program = bsed_program
        subject.save(update_fields=["program"])
        get_or_create_catalog_course(professor, subject)
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:materials_hub"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "Content Management" in content
        assert subject.code in content
        assert "Select a course subject" in content
        assert "materials-library__empty" in content

    def test_hub_gated_until_subject_selected(
        self, client, professor, subject, bsed_program
    ):
        subject.program = bsed_program
        subject.save(update_fields=["program"])
        course = get_or_create_catalog_course(professor, subject)
        LearningDocument.objects.create(
            course_id=course.pk,
            subject=subject,
            created_by=professor,
            title="Hidden until subject",
            original_name="hidden.txt",
            material_type=LearningDocument.MaterialType.MODULE,
            status=LearningDocument.Status.READY,
        )
        client.force_login(professor)

        gated = client.get(reverse("analytics_professor:materials_hub"))
        gated_content = gated.content.decode()
        assert gated.status_code == 200
        assert "Hidden until subject" not in gated_content
        assert "disabled" in gated_content

        opened = client.get(
            reverse("analytics_professor:materials_hub") + f"?subject={subject.pk}"
        )
        opened_content = opened.content.decode()
        assert opened.status_code == 200
        assert "Hidden until subject" in opened_content
        assert "Upload" in opened_content

    def test_hub_upload_posts_to_selected_subject(
        self, client, professor, subject, bsed_program
    ):
        subject.program = bsed_program
        subject.save(update_fields=["program"])
        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)
        upload = SimpleUploadedFile(
            "hub-upload.txt", b"Hub upload body.", content_type="text/plain"
        )
        response = client.post(
            reverse(
                "analytics_professor:material_upload",
                kwargs={"course_pk": course.pk},
            ),
            {
                "title": "Hub notes",
                "material_type": LearningDocument.MaterialType.MODULE,
                "subject_id": subject.pk,
                "original_name": "hub-notes.txt",
                "hub_return": "1",
                "source_file": upload,
            },
        )
        assert response.status_code == 302
        assert f"subject={subject.pk}" in response.url
        doc = LearningDocument.objects.filter(course_id=course.pk).latest("created")
        assert doc.subject_id == subject.pk
        assert doc.original_name == "hub-notes.txt"

    def test_upload_accepts_subject_and_original_name(
        self, client, professor, subject
    ):
        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)
        upload = SimpleUploadedFile(
            "raw-upload.txt", b"Module content for algebra.", content_type="text/plain"
        )
        response = client.post(
            reverse(
                "analytics_professor:material_upload",
                kwargs={"course_pk": course.pk},
            ),
            {
                "title": "Algebra notes",
                "material_type": LearningDocument.MaterialType.MODULE,
                "subject_id": subject.pk,
                "original_name": "algebra-notes.txt",
                "source_file": upload,
            },
        )
        assert response.status_code == 302
        doc = LearningDocument.objects.filter(course_id=course.pk).latest("created")
        assert doc.subject_id == subject.pk
        assert doc.original_name == "algebra-notes.txt"
        assert doc.title == "Algebra notes"

    def test_detail_updates_filename_and_subject(self, client, professor, subject):
        course = get_or_create_catalog_course(professor, subject)
        doc = LearningDocument.objects.create(
            course_id=course.pk,
            subject=subject,
            created_by=professor,
            title="Old title",
            original_name="old.txt",
            material_type=LearningDocument.MaterialType.MODULE,
            status=LearningDocument.Status.READY,
        )
        client.force_login(professor)
        response = client.post(
            reverse(
                "analytics_professor:material_detail",
                kwargs={"course_pk": course.pk, "pk": doc.pk},
            ),
            {
                "action": "save",
                "title": "New title",
                "original_name": "renamed-module.txt",
                "subject_id": subject.pk,
                "material_type": LearningDocument.MaterialType.REVIEWER,
            },
        )
        assert response.status_code == 302
        doc.refresh_from_db()
        assert doc.title == "New title"
        assert doc.original_name == "renamed-module.txt"
        assert doc.material_type == LearningDocument.MaterialType.REVIEWER


def _seed_student_mistakes(question, *, students: list[User]):
    topic = question.topic
    for student in students:
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty=question.difficulty,
            mode=ReviewSession.Mode.TIMED_EXAM,
            status=ReviewSession.Status.COMPLETED,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            is_correct=False,
            confidence=1,
        )
        MistakeRecord.objects.create(
            student=student,
            question=question,
            topic=topic,
            answer=answer,
            ai_feedback='{"feedback":"Slow down on this concept."}',
        )


@pytest.mark.django_db
class TestMistakeThresholdAndFeedback:
    @override_settings(QUESTION_MISTAKE_STUDENT_THRESHOLD=3)
    def test_distinct_student_count_not_total_attempts(
        self, student, topic, mcq_question
    ):
        question, _choice = mcq_question
        other = User.objects.create_user(
            email="student_b@example.com",
            password="pass",
            role=User.Role.STUDENT,
        )
        _seed_student_mistakes(question, students=[student, student, other])
        # Two records for same student + one other → 2 distinct students, 3 records
        assert question.mistake_records.count() == 3
        assert distinct_student_mistake_count(question) == 2
        assert question_needs_revision(question) is False

        third = User.objects.create_user(
            email="student_c@example.com",
            password="pass",
            role=User.Role.STUDENT,
        )
        _seed_student_mistakes(question, students=[third])
        assert distinct_student_mistake_count(question) == 3
        assert question_needs_revision(question) is True

        summary = question_feedback_summary(question)
        assert summary["unique_students"] == 3
        assert summary["needs_revision"] is True
        assert summary["sample_feedback"]

    @override_settings(QUESTION_MISTAKE_STUDENT_THRESHOLD=3)
    def test_edit_page_shows_revision_banner(
        self, client, professor, student, subject, mcq_question
    ):
        question, _choice = mcq_question
        course = get_or_create_catalog_course(professor, subject)
        students = [student]
        for index in range(2):
            students.append(
                User.objects.create_user(
                    email=f"misser_{index}@example.com",
                    password="pass",
                    role=User.Role.STUDENT,
                )
            )
        _seed_student_mistakes(question, students=students)

        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:question_edit",
                kwargs={"course_pk": course.pk, "question_pk": question.pk},
            )
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "should be revised" in content
        assert "Regenerate question" in content
        assert "Adaptive explanation" in content
        assert "Step-by-step" in content
        assert "Faculty expert attestation" not in content
        assert "Faculty feedback" not in content


@pytest.mark.django_db
class TestQuestionAdaptiveExplanationEdit:
    def test_edit_saves_adaptive_explanation_and_steps_without_attest(
        self, client, professor, subject, mcq_question
    ):
        from apps.questions.models import ExplanationStep, Question

        question, _choice = mcq_question
        question.status = Question.Status.APPROVED
        question.is_active = True
        question.save(update_fields=["status", "is_active"])
        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)

        choices = list(question.choices.order_by("label"))
        post_data = {
            "topic": question.topic_id,
            "difficulty": question.difficulty,
            "question_type": question.question_type,
            "stem": question.stem,
            "concept_tag": question.concept_tag or "",
            "expected_answer": "",
            "is_active": "on",
            "adaptive_what_went_wrong": "Sign error on the second term.",
            "adaptive_why": "Subtracting a negative flips the sign.",
            "adaptive_quick_check": "Try 5 - (-2).",
            "adaptive_remember": "Minus a negative adds.",
            "adaptive_worked_example": "5 - (-2) = 7.",
            "choices-TOTAL_FORMS": str(len(choices)),
            "choices-INITIAL_FORMS": str(len(choices)),
            "choices-MIN_NUM_FORMS": "0",
            "choices-MAX_NUM_FORMS": "4",
            "steps-TOTAL_FORMS": "1",
            "steps-INITIAL_FORMS": "0",
            "steps-MIN_NUM_FORMS": "0",
            "steps-MAX_NUM_FORMS": "1000",
            "steps-0-order": "1",
            "steps-0-content": "Rewrite the expression carefully.",
            "steps-0-professor_note": "Keep this short.",
            "steps-0-DELETE": "",
        }
        for index, choice in enumerate(choices):
            post_data[f"choices-{index}-id"] = str(choice.pk)
            post_data[f"choices-{index}-text"] = choice.text
            post_data[f"choices-{index}-error_type"] = ""
            if choice.is_correct:
                post_data[f"choices-{index}-is_correct"] = "on"

        response = client.post(
            reverse(
                "analytics_professor:question_edit",
                kwargs={"course_pk": course.pk, "question_pk": question.pk},
            ),
            post_data,
        )
        assert response.status_code == 302, response.content.decode()[:500]
        question.refresh_from_db()
        assert question.adaptive_explanation["what_went_wrong"] == (
            "Sign error on the second term."
        )
        assert question.adaptive_explanation["remember"] == "Minus a negative adds."
        assert question.status == Question.Status.APPROVED
        step = ExplanationStep.objects.get(question=question)
        assert "Rewrite the expression" in step.content
        assert question.explanation_status == "faculty_approved"

    def test_draft_edit_saves_adaptive_explanation_and_steps(
        self, client, professor, subject, mcq_question
    ):
        from apps.questions.models import ExplanationStep, Question

        question, _choice = mcq_question
        question.status = Question.Status.DRAFT
        question.is_active = False
        question.save(update_fields=["status", "is_active"])
        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)

        get_response = client.get(
            reverse(
                "analytics_professor:question_edit",
                kwargs={"course_pk": course.pk, "question_pk": question.pk},
            )
        )
        assert get_response.status_code == 200
        content = get_response.content.decode()
        assert "Adaptive explanation" in content
        assert "Step-by-step" in content

        choices = list(question.choices.order_by("label"))
        post_data = {
            "topic": question.topic_id,
            "difficulty": question.difficulty,
            "question_type": question.question_type,
            "stem": question.stem,
            "concept_tag": question.concept_tag or "",
            "expected_answer": "",
            "adaptive_what_went_wrong": "Draft wrong path.",
            "adaptive_why": "Draft why text.",
            "adaptive_quick_check": "Draft check.",
            "adaptive_remember": "Draft hook.",
            "adaptive_worked_example": "Draft example.",
            "choices-TOTAL_FORMS": str(len(choices)),
            "choices-INITIAL_FORMS": str(len(choices)),
            "choices-MIN_NUM_FORMS": "0",
            "choices-MAX_NUM_FORMS": "4",
            "steps-TOTAL_FORMS": "1",
            "steps-INITIAL_FORMS": "0",
            "steps-MIN_NUM_FORMS": "0",
            "steps-MAX_NUM_FORMS": "1000",
            "steps-0-order": "1",
            "steps-0-content": "Draft step one.",
            "steps-0-professor_note": "",
            "steps-0-DELETE": "",
        }
        for index, choice in enumerate(choices):
            post_data[f"choices-{index}-id"] = str(choice.pk)
            post_data[f"choices-{index}-text"] = choice.text
            post_data[f"choices-{index}-error_type"] = ""
            if choice.is_correct:
                post_data[f"choices-{index}-is_correct"] = "on"

        response = client.post(
            reverse(
                "analytics_professor:question_edit",
                kwargs={"course_pk": course.pk, "question_pk": question.pk},
            ),
            post_data,
        )
        assert response.status_code == 302, response.content.decode()[:500]
        question.refresh_from_db()
        assert question.status == Question.Status.DRAFT
        assert question.adaptive_explanation["what_went_wrong"] == "Draft wrong path."
        assert ExplanationStep.objects.filter(
            question=question, content__contains="Draft step"
        ).exists()

    def test_create_form_shows_and_saves_adaptive_fields(
        self, client, professor, subject, topic
    ):
        from apps.questions.models import ExplanationStep, Question

        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)

        get_response = client.get(
            reverse(
                "analytics_professor:question_create_single",
                kwargs={"course_pk": course.pk},
            )
        )
        assert get_response.status_code == 200
        content = get_response.content.decode()
        assert "Adaptive explanation" in content
        assert "Step-by-step" in content
        assert "1 Details" in content
        assert "3 Explanation" in content
        assert 'data-question-edit-tabs' in content

        post_data = {
            "topic": topic.pk,
            "difficulty": Question.Difficulty.EASY,
            "question_type": Question.QuestionType.MCQ,
            "stem": "What is 2 + 2?",
            "concept_tag": "addition",
            "expected_answer": "",
            "adaptive_what_went_wrong": "Added instead of multiplied.",
            "adaptive_why": "The operation is addition.",
            "adaptive_quick_check": "2+2=4",
            "adaptive_remember": "Plus means add.",
            "adaptive_worked_example": "2 + 2 = 4.",
            "choices-TOTAL_FORMS": "4",
            "choices-INITIAL_FORMS": "0",
            "choices-MIN_NUM_FORMS": "0",
            "choices-MAX_NUM_FORMS": "4",
            "choices-0-text": "3",
            "choices-0-error_type": "",
            "choices-1-text": "4",
            "choices-1-is_correct": "on",
            "choices-1-error_type": "",
            "choices-2-text": "5",
            "choices-2-error_type": "",
            "choices-3-text": "22",
            "choices-3-error_type": "",
            "steps-TOTAL_FORMS": "1",
            "steps-INITIAL_FORMS": "0",
            "steps-MIN_NUM_FORMS": "0",
            "steps-MAX_NUM_FORMS": "1000",
            "steps-0-order": "1",
            "steps-0-content": "Add the ones place.",
            "steps-0-professor_note": "",
            "steps-0-DELETE": "",
        }
        response = client.post(
            reverse(
                "analytics_professor:question_create_single",
                kwargs={"course_pk": course.pk},
            ),
            post_data,
        )
        assert response.status_code == 302, response.content.decode()[:800]
        question = Question.objects.filter(stem="What is 2 + 2?").latest("pk")
        assert question.status == Question.Status.DRAFT
        assert question.adaptive_explanation["remember"] == "Plus means add."
        assert ExplanationStep.objects.filter(
            question=question, content__contains="ones place"
        ).exists()

    def test_batch_draft_edit_shows_explanation_tabs(
        self, client, professor, subject
    ):
        course = get_or_create_catalog_course(professor, subject)
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:question_batch_edit",
                kwargs={"course_pk": course.pk, "question_index": 0},
            )
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "1 Details" in content
        assert "3 Explanation" in content
        assert "4 Steps" in content
        assert "What went wrong" in content
        assert "edit-adaptive-what-went-wrong" in content
        assert "edit-steps-list" in content



@pytest.mark.django_db
class TestMistakeThresholdNotification:
    @override_settings(QUESTION_MISTAKE_STUDENT_THRESHOLD=3)
    def test_log_mistake_notifies_faculty_with_edit_link(
        self, professor, student, subject, mcq_question
    ):
        from apps.analytics.services import log_mistake
        from apps.users.models import Notification

        question, _correct = mcq_question
        wrong = question.choices.exclude(is_correct=True).first()
        course = get_or_create_catalog_course(professor, subject)
        students = [student]
        for index in range(2):
            students.append(
                User.objects.create_user(
                    email=f"notify_miss_{index}@example.com",
                    password="pass",
                    role=User.Role.STUDENT,
                )
            )

        # Seed two distinct students via direct records (below threshold).
        _seed_student_mistakes(question, students=students[:2])
        assert Notification.objects.filter(user=professor).count() == 0

        # Third unique student crosses threshold via log_mistake.
        third = students[2]
        session = ReviewSession.objects.create(
            student=third,
            topic=question.topic,
            difficulty=question.difficulty,
            mode=ReviewSession.Mode.TIMED_EXAM,
            status=ReviewSession.Status.COMPLETED,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            is_correct=False,
            confidence=1,
        )
        log_mistake(third, question, answer)

        notes = Notification.objects.filter(user=professor)
        assert notes.count() == 1
        note = notes.get()
        assert "3+ students missed" in note.message
        assert subject.code in note.message
        expected_link = reverse(
            "analytics_professor:question_edit",
            kwargs={"course_pk": course.pk, "question_pk": question.pk},
        )
        assert note.link == expected_link

        # Deduplicate: another miss by same student should not create another unread.
        session2 = ReviewSession.objects.create(
            student=third,
            topic=question.topic,
            difficulty=question.difficulty,
            mode=ReviewSession.Mode.TIMED_EXAM,
            status=ReviewSession.Status.COMPLETED,
        )
        answer2 = Answer.objects.create(
            session=session2,
            question=question,
            selected_choice=wrong,
            is_correct=False,
            confidence=1,
        )
        log_mistake(third, question, answer2)
        assert Notification.objects.filter(user=professor).count() == 1


@pytest.mark.django_db
class TestQuestionRegenerate:
    @override_settings(QUESTION_MISTAKE_STUDENT_THRESHOLD=2)
    def test_regenerate_starts_job_with_reference_stem(
        self, client, professor, student, subject, mcq_question
    ):
        question, _choice = mcq_question
        course = get_or_create_catalog_course(professor, subject)
        other = User.objects.create_user(
            email="regen_peer@example.com",
            password="pass",
            role=User.Role.STUDENT,
        )
        _seed_student_mistakes(question, students=[student, other])

        client.force_login(professor)
        with patch(
            "apps.ai.job_services.run_question_generation_job",
            autospec=True,
        ):
            response = client.post(
                reverse(
                    "analytics_professor:question_regenerate",
                    kwargs={"course_pk": course.pk, "question_pk": question.pk},
                )
            )
        assert response.status_code == 202
        payload = response.json()
        job = AIGenerationJob.objects.get(pk=payload["job_id"])
        assert job.reference_stem == question.stem
        assert job.reference_question_id == question.pk
        assert job.difficulty == question.difficulty
        assert job.count == 3

    @override_settings(QUESTION_MISTAKE_STUDENT_THRESHOLD=2)
    def test_regenerate_blocked_below_threshold(
        self, client, professor, student, subject, mcq_question
    ):
        question, _choice = mcq_question
        course = get_or_create_catalog_course(professor, subject)
        _seed_student_mistakes(question, students=[student])
        client.force_login(professor)
        response = client.post(
            reverse(
                "analytics_professor:question_regenerate",
                kwargs={"course_pk": course.pk, "question_pk": question.pk},
            )
        )
        assert response.status_code == 400
        assert "unlocks after" in response.json()["error"]

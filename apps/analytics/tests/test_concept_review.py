"""Tests for Concepts to Review (Learn → Try it → Practice)."""

import json

import pytest
from django.urls import reverse

from apps.analytics.concept_review_services import (
    CORRECT_TO_RESOLVE,
    build_concept_card_context,
    concept_key_for_question,
    ensure_learn_content,
    record_exam_miss_for_concept,
    restart_concept_review,
    start_or_next_practice,
    submit_practice_answer,
    submit_try_it,
)
from apps.analytics.models import ConceptReview
from apps.analytics.services import log_mistake
from apps.reviews.models import Answer, ReviewSession


@pytest.mark.django_db
class TestConceptKey:
    def test_uses_concept_tag_when_present(self, mcq_question):
        question, _ = mcq_question
        question.concept_tag = "Two-step equations"
        question.save(update_fields=["concept_tag"])
        key, name = concept_key_for_question(question)
        assert key == "two-step equations"
        assert name == "Two-step equations"

    def test_falls_back_to_topic(self, mcq_question):
        question, _ = mcq_question
        question.concept_tag = ""
        question.save(update_fields=["concept_tag"])
        key, name = concept_key_for_question(question)
        assert key == f"topic:{question.topic_id}"
        assert name == question.topic.name


@pytest.mark.django_db
class TestRecordExamMiss:
    def _wrong_answer(self, student, mcq_question, *, confidence=5):
        question, _ = mcq_question
        wrong = question.choices.exclude(is_correct=True).first()
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        return Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            confidence=confidence,
            is_correct=False,
        ), question, wrong

    def test_log_mistake_creates_concept_review(self, student, mcq_question):
        answer, question, _ = self._wrong_answer(student, mcq_question)
        question.concept_tag = "Linear equations"
        question.save(update_fields=["concept_tag"])
        log_mistake(student, question, answer)
        review = ConceptReview.objects.get(student=student)
        assert review.concept_name == "Linear equations"
        assert review.miss_count == 1
        assert review.status == ConceptReview.Status.NEEDS_REVIEW
        assert review.marked_sure_count == 1

    def test_reopens_resolved_on_new_miss(self, student, mcq_question):
        answer, question, _ = self._wrong_answer(student, mcq_question)
        question.concept_tag = "Integrals"
        question.save(update_fields=["concept_tag"])
        review = record_exam_miss_for_concept(student, question, answer)
        review.status = ConceptReview.Status.RESOLVED
        review.correct_streak = 3
        review.save()

        answer2, _, _ = self._wrong_answer(student, mcq_question, confidence=1)
        review = record_exam_miss_for_concept(student, question, answer2)
        assert review.status == ConceptReview.Status.NEEDS_REVIEW
        assert review.correct_streak == 0
        assert review.miss_count == 2


@pytest.mark.django_db
class TestLearnTryPractice:
    @pytest.fixture(autouse=True)
    def _disable_ai(self, settings):
        settings.AI_ENABLED = False

    def _review(self, student, mcq_question):
        question, _ = mcq_question
        question.concept_tag = "Two-step linear equations"
        question.save(update_fields=["concept_tag"])
        wrong = question.choices.exclude(is_correct=True).first()
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        return record_exam_miss_for_concept(student, question, answer, error_slug="sign_error")

    def test_ensure_learn_content_caches_stub(self, student, mcq_question):
        review = self._review(student, mcq_question)
        ensure_learn_content(review)
        review.refresh_from_db()
        assert review.learn_payload.get("try_it")
        assert review.diagnosis_type
        assert review.feedback_styles_used

    def test_try_it_advances_on_correct(self, student, mcq_question):
        review = self._review(student, mcq_question)
        ensure_learn_content(review)
        correct_index = review.try_it_payload["correct_index"]
        result = submit_try_it(review, correct_index)
        assert result["is_correct"] is True
        review.refresh_from_db()
        assert review.current_step == ConceptReview.Step.PRACTICE

    def test_practice_resolves_after_three_correct(self, student, mcq_question):
        review = self._review(student, mcq_question)
        ensure_learn_content(review)
        for _ in range(CORRECT_TO_RESOLVE):
            attempt = start_or_next_practice(review)
            correct = next(
                o for o in attempt.question_payload["options"] if o.get("is_correct")
            )
            result = submit_practice_answer(review, attempt, correct["id"])
            assert result["is_correct"] is True
        review.refresh_from_db()
        assert review.status == ConceptReview.Status.RESOLVED
        assert review.correct_streak == 3
        assert review.recheck_due_at is not None

    def test_wrong_practice_holds_streak(self, student, mcq_question):
        review = self._review(student, mcq_question)
        ensure_learn_content(review)
        attempt = start_or_next_practice(review)
        correct = next(
            o for o in attempt.question_payload["options"] if o.get("is_correct")
        )
        submit_practice_answer(review, attempt, correct["id"])
        review.refresh_from_db()
        assert review.correct_streak == 1

        attempt2 = start_or_next_practice(review)
        wrong = next(
            o for o in attempt2.question_payload["options"] if not o.get("is_correct")
        )
        submit_practice_answer(review, attempt2, wrong["id"])
        review.refresh_from_db()
        assert review.correct_streak == 1
        assert review.status == ConceptReview.Status.PRACTICING

    def test_restart_clears_learn_cache(self, student, mcq_question):
        review = self._review(student, mcq_question)
        ensure_learn_content(review)
        review.status = ConceptReview.Status.RESOLVED
        review.correct_streak = 3
        review.save()
        restart_concept_review(review)
        review.refresh_from_db()
        assert review.status == ConceptReview.Status.NEEDS_REVIEW
        assert review.learn_payload == {}
        assert review.correct_streak == 0

    def test_card_context_badge(self, student, mcq_question):
        review = self._review(student, mcq_question)
        review.diagnosis_type = ConceptReview.DiagnosisType.MISCONCEPTION
        review.save(update_fields=["diagnosis_type"])
        card = build_concept_card_context(review)
        assert card["badge"] == "Likely misconception"
        assert "Start review" in card["cta"]


@pytest.mark.django_db
class TestConceptReviewViews:
    @pytest.fixture(autouse=True)
    def _disable_ai(self, settings):
        settings.AI_ENABLED = False

    def test_mistakes_concepts_tab(self, client, student, mcq_question):
        question, _ = mcq_question
        question.concept_tag = "Modular arithmetic"
        question.save(update_fields=["concept_tag"])
        wrong = question.choices.exclude(is_correct=True).first()
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        log_mistake(student, question, answer)
        client.force_login(student)
        response = client.get(
            reverse("analytics_student:mistakes"),
            {"tab": "concepts"},
        )
        assert response.status_code == 200
        assert b"Concepts to Review" in response.content
        assert b"Modular arithmetic" in response.content

    def test_concept_detail_learn_step(self, client, student, mcq_question):
        question, _ = mcq_question
        question.concept_tag = "Factoring"
        question.save(update_fields=["concept_tag"])
        wrong = question.choices.exclude(is_correct=True).first()
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            confidence=1,
            is_correct=False,
        )
        review = record_exam_miss_for_concept(student, question, answer)
        client.force_login(student)
        response = client.get(
            reverse("analytics_student:concept_review", kwargs={"pk": review.pk}),
            {"step": "learn"},
        )
        assert response.status_code == 200
        assert b"Continue to Try it" in response.content

    def test_student_cannot_view_others_review(
        self, client, student, professor, mcq_question, department, year_level, program_section
    ):
        from apps.users.models import User

        other = User.objects.create_user(
            email="other-student@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
            department=department,
            year_level=year_level,
            section=program_section,
        )
        question, _ = mcq_question
        question.concept_tag = "Private concept"
        question.save(update_fields=["concept_tag"])
        wrong = question.choices.exclude(is_correct=True).first()
        session = ReviewSession.objects.create(
            student=other,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        review = record_exam_miss_for_concept(other, question, answer)
        client.force_login(student)
        response = client.get(
            reverse("analytics_student:concept_review", kwargs={"pk": review.pk})
        )
        assert response.status_code == 404
        _ = professor

    def test_try_it_post_json(self, client, student, mcq_question):
        question, _ = mcq_question
        question.concept_tag = "Order of operations"
        question.save(update_fields=["concept_tag"])
        wrong = question.choices.exclude(is_correct=True).first()
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            selected_choice=wrong,
            confidence=5,
            is_correct=False,
        )
        review = record_exam_miss_for_concept(student, question, answer)
        ensure_learn_content(review)
        correct_index = review.try_it_payload["correct_index"]
        client.force_login(student)
        response = client.post(
            reverse("analytics_student:concept_review_try_it", kwargs={"pk": review.pk}),
            data=json.dumps({"choice_index": correct_index}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["is_correct"] is True

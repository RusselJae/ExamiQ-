"""Faculty (Professor) role test cases — Question Bank module.

Maps to the manual test-case table ``docs/role-test-cases.md`` (Appendix A.2),
rows TC-F03 to TC-F05:

* TC-F03 Manage topics
* TC-F04 Create question
* TC-F05 Publish question (faculty attestation)
"""

import pytest
from django.urls import reverse

from apps.questions.models import Question, Topic


@pytest.mark.django_db
class TestFacultyTopics:
    """TC-F03 — Manage course topics."""

    def test_topic_list_shows_course_topics(
        self, client, professor, teaching_assignment, topic
    ):
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.get(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course.pk})
        )

        assert response.status_code == 200
        listed = list(response.context["topics"])
        assert topic.pk in [row.pk for row in listed]

    def test_create_topic_saves_it_under_the_course_subject(
        self, client, professor, teaching_assignment
    ):
        course = teaching_assignment.course
        subject = course.teaching_assignment.subject
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:topic_create", kwargs={"course_pk": course.pk}
            ),
            {"name": "Limits and Continuity"},
        )

        assert response.status_code == 302
        assert Topic.objects.filter(
            subject=subject, name="Limits and Continuity"
        ).exists()

    def test_create_topic_rejects_an_empty_name(
        self, client, professor, teaching_assignment
    ):
        """Actual error: blank topic name."""
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:topic_create", kwargs={"course_pk": course.pk}
            ),
            {"name": ""},
        )

        assert response.status_code == 302
        assert not Topic.objects.filter(name="").exists()

    def test_create_topic_rejects_a_duplicate_name(
        self, client, professor, teaching_assignment, topic
    ):
        """Actual error: duplicate topic name for the same course."""
        course = teaching_assignment.course
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:topic_create", kwargs={"course_pk": course.pk}
            ),
            {"name": topic.name},
            HTTP_ACCEPT="application/json",
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["error"]

    def test_faculty_cannot_open_another_professors_course_topics(
        self, client, professor, chairperson, teaching_assignment
    ):
        """Actual error: course owned by another user."""
        course = teaching_assignment.course
        client.force_login(chairperson)

        response = client.get(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course.pk})
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestFacultyCreateQuestion:
    """TC-F04 — Create a question in the course question bank."""

    @pytest.fixture
    def course(self, teaching_assignment):
        return teaching_assignment.course

    def test_question_list_renders_for_the_course(self, client, professor, course):
        client.force_login(professor)

        response = client.get(
            reverse(
                "analytics_professor:question_list", kwargs={"course_pk": course.pk}
            )
        )

        assert response.status_code == 200

    def test_create_question_saves_a_draft(self, client, professor, course, topic):
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:question_create_single",
                kwargs={"course_pk": course.pk},
            ),
            {
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "What is the derivative of x squared?",
                "concept_tag": "derivatives",
                "choices-TOTAL_FORMS": 4,
                "choices-INITIAL_FORMS": 0,
                "choices-MIN_NUM_FORMS": 0,
                "choices-MAX_NUM_FORMS": 4,
                "choices-0-text": "2x",
                "choices-0-is_correct": "on",
                "choices-1-text": "x",
                "choices-2-text": "2",
                "choices-3-text": "x^3",
                "steps-TOTAL_FORMS": 1,
                "steps-INITIAL_FORMS": 0,
                "steps-MIN_NUM_FORMS": 0,
                "steps-MAX_NUM_FORMS": 6,
                "steps-0-order": 1,
                "steps-0-content": "Apply the power rule.",
            },
        )

        assert response.status_code == 302
        question = Question.objects.get(stem="What is the derivative of x squared?")
        assert question.status == Question.Status.DRAFT
        assert question.is_active is False
        assert question.proposed_by == professor
        assert question.choices.count() == 4
        assert question.choices.get(is_correct=True).text == "2x"

    def test_create_question_requires_two_choices(
        self, client, professor, course, topic
    ):
        """Actual error: not enough answer choices."""
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:question_create_single",
                kwargs={"course_pk": course.pk},
            ),
            {
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "A question with a single choice.",
                "choices-TOTAL_FORMS": 1,
                "choices-INITIAL_FORMS": 0,
                "choices-MIN_NUM_FORMS": 0,
                "choices-MAX_NUM_FORMS": 4,
                "choices-0-text": "Only one",
                "choices-0-is_correct": "on",
                "steps-TOTAL_FORMS": 0,
                "steps-INITIAL_FORMS": 0,
                "steps-MIN_NUM_FORMS": 0,
                "steps-MAX_NUM_FORMS": 6,
            },
        )

        assert response.status_code == 200
        assert "Provide at least two answer choices." in response.content.decode()
        assert not Question.objects.filter(
            stem="A question with a single choice."
        ).exists()

    def test_create_question_requires_a_correct_choice(
        self, client, professor, course, topic
    ):
        """Actual error: no choice marked as correct."""
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:question_create_single",
                kwargs={"course_pk": course.pk},
            ),
            {
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "A question with no correct answer.",
                "choices-TOTAL_FORMS": 2,
                "choices-INITIAL_FORMS": 0,
                "choices-MIN_NUM_FORMS": 0,
                "choices-MAX_NUM_FORMS": 4,
                "choices-0-text": "First",
                "choices-1-text": "Second",
                "steps-TOTAL_FORMS": 0,
                "steps-INITIAL_FORMS": 0,
                "steps-MIN_NUM_FORMS": 0,
                "steps-MAX_NUM_FORMS": 6,
            },
        )

        assert response.status_code == 200
        assert "Mark one choice as correct." in response.content.decode()
        assert not Question.objects.filter(
            stem="A question with no correct answer."
        ).exists()

    def test_create_question_is_blocked_on_another_professors_course(
        self, client, professor, chairperson, course, topic
    ):
        """Actual error: course owned by another user."""
        client.force_login(chairperson)

        response = client.get(
            reverse(
                "analytics_professor:question_create_single",
                kwargs={"course_pk": course.pk},
            )
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestFacultyPublishQuestion:
    """TC-F05 — Publish a draft question after faculty attestation."""

    @pytest.fixture
    def course(self, teaching_assignment):
        return teaching_assignment.course

    @pytest.fixture
    def draft_question(self, course, topic):
        return Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Draft question awaiting attestation.",
            status=Question.Status.DRAFT,
            is_active=False,
        )

    def test_publish_requires_faculty_attestation(
        self, client, professor, course, draft_question
    ):
        """Actual error: attestation checkbox not ticked."""
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:question_publish",
                kwargs={"course_pk": course.pk, "question_pk": draft_question.pk},
            ),
            {},
        )

        assert response.status_code == 302
        draft_question.refresh_from_db()
        assert draft_question.status == Question.Status.DRAFT
        assert draft_question.is_active is False

    def test_publish_with_attestation_approves_the_question(
        self, client, professor, course, draft_question
    ):
        client.force_login(professor)

        response = client.post(
            reverse(
                "analytics_professor:question_publish",
                kwargs={"course_pk": course.pk, "question_pk": draft_question.pk},
            ),
            {"faculty_attest": "1"},
        )

        assert response.status_code == 302
        draft_question.refresh_from_db()
        assert draft_question.status == Question.Status.APPROVED
        assert draft_question.is_active is True
        assert draft_question.validated_by == professor

    def test_publish_is_blocked_for_another_professors_course(
        self, client, professor, chairperson, course, draft_question
    ):
        """Actual error: course owned by another user."""
        client.force_login(chairperson)

        response = client.post(
            reverse(
                "analytics_professor:question_publish",
                kwargs={"course_pk": course.pk, "question_pk": draft_question.pk},
            ),
            {"faculty_attest": "1"},
        )

        assert response.status_code == 404
        draft_question.refresh_from_db()
        assert draft_question.status == Question.Status.DRAFT

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.analytics.confidence import (
    CLASSIFICATION_LUCKY_GUESS,
    CLASSIFICATION_MASTERY,
    CLASSIFICATION_MISCONCEPTION,
    CONFIDENCE_TIER_HIGH,
    CONFIDENCE_TIER_LOW,
    CONFIDENCE_TIER_AVERAGE,
    classify_answer,
    confidence_accuracy_matrix,
    confidence_tier_matrix,
)
from apps.analytics.models import ErrorType
from apps.analytics.services import (
    get_step_feedback_stats,
    get_topic_mastery_heatmap,
    log_mistake,
    student_course_summary,
)
from apps.core.context_processors import navigation_context
from apps.questions.models import ExplanationStep, Question
from apps.reviews.models import Answer, ReviewSession, StepFeedbackView
from apps.users.models import Course


@pytest.mark.django_db
class TestConfidenceMatrix:
    def test_classify_answer_high_correct(self):
        assert classify_answer(5, True) == CLASSIFICATION_MASTERY

    def test_classify_answer_high_wrong(self):
        assert classify_answer(5, False) == CLASSIFICATION_MISCONCEPTION

    def test_classify_answer_low_correct(self):
        assert classify_answer(1, True) == CLASSIFICATION_LUCKY_GUESS

    def test_classify_answer_medium(self):
        from apps.analytics.confidence import CLASSIFICATION_UNCERTAIN

        assert classify_answer(3, True) == CLASSIFICATION_UNCERTAIN

    def test_confidence_accuracy_matrix(self, student, mcq_question, numeric_question):
        question, _correct = mcq_question
        numeric_q = numeric_question
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(
            session=session,
            question=question,
            confidence=5,
            is_correct=False,
        )
        Answer.objects.create(
            session=session,
            question=numeric_q,
            confidence=5,
            is_correct=True,
        )
        matrix = confidence_accuracy_matrix(Answer.objects.filter(session=session))
        assert matrix[CLASSIFICATION_MISCONCEPTION] == 1
        assert matrix[CLASSIFICATION_MASTERY] == 1

    def test_confidence_tier_matrix(self, student, mcq_question, numeric_question):
        question, _correct = mcq_question
        numeric_q = numeric_question
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(
            session=session,
            question=question,
            confidence=5,
            is_correct=False,
        )
        Answer.objects.create(
            session=session,
            question=numeric_q,
            confidence=3,
            is_correct=True,
        )
        matrix = confidence_tier_matrix(Answer.objects.filter(session=session))
        assert matrix[CONFIDENCE_TIER_HIGH] == 1
        assert matrix[CONFIDENCE_TIER_AVERAGE] == 1


@pytest.mark.django_db
class TestExamSetupProfessor:
    def test_professor_can_save_exam_setup(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk}),
            {
                "is_enabled": True,
                "seconds_per_question": 30,
                "allowed_difficulties": ["easy", "medium", "hard"],
            },
        )
        assert response.status_code == 302
        setup = course.exam_setup
        assert setup.is_enabled is True

    def test_other_professor_cannot_access_exam_setup(
        self, client, professor, chairperson, teaching_assignment
    ):
        course = teaching_assignment.course
        client.force_login(chairperson)
        response = client.get(
            reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestProfessorRoster:
    def test_roster_lists_practicing_students(self, client, professor, student, program, topic):
        course = Course.objects.create(
            program=program,
            code="ROST101",
            name="Roster Course",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="A",
        )
        ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty="easy",
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_roster", kwargs={"course_pk": course.pk}))
        assert response.status_code == 200
        content = response.content.decode()
        assert student.email in content
        assert "Masterlist" in content

    def test_student_detail_requires_session(self, client, professor, student, program):
        course = Course.objects.create(
            program=program,
            code="DET101",
            name="Detail Course",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="A",
        )
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:student_detail",
                kwargs={"course_pk": course.pk, "student_pk": student.pk},
            )
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestSidebarContext:
    def test_sidebar_course_set_on_roster_url(self, rf, professor, student, program):
        course = Course.objects.create(
            program=program,
            code="NAV101",
            name="Nav Course",
            professor=professor,
        )
        request = rf.get(
            reverse("analytics_professor:course_roster", kwargs={"course_pk": course.pk})
        )
        request.user = professor
        request.resolver_match = MagicMock(
            namespace="analytics_professor",
            kwargs={"course_pk": course.pk},
            url_name="course_roster",
        )
        context = navigation_context(request)
        assert context["sidebar_course"].pk == course.pk
        assert len(context["professor_courses"]) == 1


@pytest.mark.django_db
class TestHeatmap:
    def test_heatmap_counts_confidence_tiers(self, student, mcq_question, program, professor):
        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="HEAT101",
            name="Heatmap Course",
            professor=professor,
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(session=session, question=question, confidence=5, is_correct=False)
        heatmap = get_topic_mastery_heatmap(course)
        topic_row = next(t for t in heatmap["topics"] if t["topic_name"] == question.topic.name)
        assert topic_row["high"] >= 1

    def test_student_rows_include_practicing_student(self, student, mcq_question, program, professor):
        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="HEAT102",
            name="Heatmap Students",
            professor=professor,
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(session=session, question=question, confidence=5, is_correct=False)
        heatmap = get_topic_mastery_heatmap(course)
        assert any(row["student_id"] == student.pk for row in heatmap["student_rows"])


@pytest.mark.django_db
class TestQuestionCRUD:
    @override_settings(AI_ENABLED=False)
    def test_professor_can_create_question(self, client, professor, topic, program):
        course = Course.objects.create(
            program=program,
            code="QB101",
            name="QB Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:question_create", kwargs={"course_pk": course.pk}),
            {
                "topic": topic.id,
                "difficulty": Question.Difficulty.EASY,
                "question_count": 1,
                "stem_0": "Test question?",
                "correct_0": "A",
                "concept_tag_0": "Test concept",
                "choice_0_A": "1",
                "choice_0_B": "2",
                "choice_0_C": "3",
                "choice_0_D": "4",
            },
        )
        assert response.status_code == 302, getattr(response, "context", None)
        assert Question.objects.filter(stem="Test question?").exists()

    @override_settings(AI_ENABLED=False)
    def test_batch_skips_duplicate_question(self, client, professor, topic, program):
        course = Course.objects.create(
            program=program,
            code="QB103",
            name="QB Course 3",
            professor=professor,
        )
        from apps.questions.services import create_question

        create_question(
            {
                "topic": topic,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "Existing question?",
                "is_active": True,
                "status": Question.Status.APPROVED,
            },
            [
                {"label": "A", "text": "1", "is_correct": True},
                {"label": "B", "text": "2", "is_correct": False},
                {"label": "C", "text": "3", "is_correct": False},
                {"label": "D", "text": "4", "is_correct": False},
            ],
            [],
        )
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:question_create", kwargs={"course_pk": course.pk}),
            {
                "topic": topic.id,
                "difficulty": Question.Difficulty.EASY,
                "question_count": 1,
                "stem_0": "existing question?",
                "correct_0": "A",
                "choice_0_A": "1",
                "choice_0_B": "2",
                "choice_0_C": "3",
                "choice_0_D": "4",
            },
            follow=True,
        )
        assert response.status_code == 200
        assert Question.objects.filter(stem__iexact="existing question?").count() == 1

    def test_ai_validate_returns_json(self, client, professor, topic, program):
        course = Course.objects.create(
            program=program,
            code="QB104",
            name="QB Course 4",
            professor=professor,
        )
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:question_ai_validate", kwargs={"course_pk": course.pk}),
            {
                "topic": topic.id,
                "difficulty": Question.Difficulty.EASY,
                "stem": "What is 2+2?",
                "correct_label": "A",
                "choice_A": "4",
                "choice_B": "5",
                "choice_C": "6",
                "choice_D": "7",
            },
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_valid" in data
        assert "feedback" in data

    def test_professor_can_create_question_with_error_type(self, client, professor, topic, program):
        course = Course.objects.create(
            program=program,
            code="QB102",
            name="QB Course 2",
            professor=professor,
        )
        error_type = ErrorType.objects.create(slug="unit", label="Unit error", category="procedural")
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:question_create_single", kwargs={"course_pk": course.pk}),
            {
                "topic": topic.id,
                "difficulty": Question.Difficulty.EASY,
                "question_type": Question.QuestionType.MCQ,
                "stem": "Error type question?",
                "is_active": "on",
                "choices-TOTAL_FORMS": 4,
                "choices-INITIAL_FORMS": 0,
                "choices-MIN_NUM_FORMS": 0,
                "choices-MAX_NUM_FORMS": 4,
                "choices-0-label": "A",
                "choices-0-text": "1",
                "choices-0-is_correct": "on",
                "choices-1-label": "B",
                "choices-1-text": "2",
                "choices-1-error_type": error_type.pk,
                "choices-2-label": "C",
                "choices-2-text": "3",
                "choices-3-label": "D",
                "choices-3-text": "4",
                "explanation_steps-TOTAL_FORMS": 0,
                "explanation_steps-INITIAL_FORMS": 0,
                "explanation_steps-MIN_NUM_FORMS": 0,
                "explanation_steps-MAX_NUM_FORMS": 1000,
            },
        )
        assert response.status_code == 302
        question = Question.objects.get(stem="Error type question?")
        wrong = question.choices.filter(label="B").first()
        assert wrong.error_type == error_type

    def test_professor_cannot_edit_other_course_questions(self, client, professor, chairperson, topic, program):
        course = Course.objects.create(
            program=program,
            code="OTH101",
            name="Other",
            professor=chairperson,
        )
        question = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="Private Q",
        )
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:question_edit",
                kwargs={"course_pk": course.pk, "question_pk": question.pk},
            )
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestErrorTypes:
    def test_log_mistake_copies_choice_error_type(self, student, mcq_question):
        question, correct = mcq_question
        wrong = question.choices.exclude(is_correct=True).first()
        error_type = ErrorType.objects.create(slug="sign", label="Sign error", category="procedural")
        wrong.error_type = error_type
        wrong.save()
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
        record = log_mistake(student, question, answer)
        assert record.error_type == error_type


@pytest.mark.django_db
class TestStepFeedbackStats:
    def test_step_views_counted(self, mcq_question, student):
        question, _ = mcq_question
        step = ExplanationStep.objects.create(question=question, order=1, content="Explain")
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            confidence=3,
            is_correct=False,
        )
        StepFeedbackView.objects.create(answer=answer, explanation_step=step)
        StepFeedbackView.objects.create(answer=answer, explanation_step=step)
        stats = get_step_feedback_stats(question)
        assert stats[0]["view_count"] == 2


@pytest.mark.django_db
class TestCourseInsights:
    def test_insights_url_redirects_to_analytics(self, client, professor, program):
        course = Course.objects.create(
            program=program,
            code="INS101",
            name="Insights Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.get(
            reverse("analytics_professor:course_insights", kwargs={"pk": course.pk})
        )
        assert response.status_code == 302
        assert response.url == reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})

    def test_analytics_does_not_auto_show_narrative(self, client, professor, program):
        course = Course.objects.create(
            program=program,
            code="INS102",
            name="Insights Course 2",
            professor=professor,
        )
        client.force_login(professor)
        response = client.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Click the lightbulb to generate your weekly summary." in content
        assert 'id="summary-fab"' in content
        assert "id=\"summary-narrative\"" not in content

    def test_summary_generate_endpoint(self, client, professor, program):
        course = Course.objects.create(
            program=program,
            code="INS103",
            name="Insights Course 3",
            professor=professor,
        )
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:course_summary_generate", kwargs={"pk": course.pk})
        )
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data
        assert len(data["narrative"]) > 0


@pytest.mark.django_db
class TestProfessorOverviewUX:
    def test_overview_includes_dates_and_course_stats(self, client, professor, program):
        course = Course.objects.create(
            program=program,
            code="OV101",
            name="Overview Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:overview"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Data as of" in content
        assert "Week of" in content
        assert "Your courses" in content
        assert course.name in content
        assert "Active courses" in content
        assert "Overall accuracy" in content
        assert "Cross-course snapshot" not in content

    def test_summary_courses_json_is_array(self, client, professor, program):
        Course.objects.create(
            program=program,
            code="JSON101",
            name="JSON Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:overview"))
        import json
        import re

        match = re.search(
            r'<script id="summary-courses-data" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        assert match
        data = json.loads(match.group(1))
        assert isinstance(data, list)
        assert data[0]["pk"]
        assert data[0]["code"] == "JSON101"

    def test_summary_fab_on_overview_when_courses_exist(self, client, professor, program):
        Course.objects.create(
            program=program,
            code="FAB101",
            name="FAB Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:overview"))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="summary-fab"' in content
        assert 'id="summary-recall-btn"' in content
        assert 'id="summary-close-btn"' in content
        assert 'id="summary-refresh-btn"' in content
        assert "analytics-summary.js" in content

    def test_summary_fab_absent_without_courses(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:overview"))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="summary-fab"' not in content


@pytest.mark.django_db
class TestAIStubs:
    def test_question_generator_returns_empty(self):
        from apps.ai.factory import get_question_generator

        assert get_question_generator().generate(None, "easy", 3) == []

    def test_curriculum_advisor_returns_text(self, program):
        from apps.ai.factory import get_curriculum_advisor

        report = get_curriculum_advisor().program_report(program)
        assert program.name in report

    @override_settings(AI_ENABLED=False, OPENAI_API_KEY="")
    def test_factory_uses_stub_when_disabled(self):
        from apps.ai.factory import get_difficulty_tagger
        from apps.ai.stubs import StubDifficultyTagger

        assert isinstance(get_difficulty_tagger(), StubDifficultyTagger)


@pytest.mark.django_db
class TestAIFactoryOpenAI:
    @override_settings(AI_ENABLED=True, LLM_PROVIDER="openai", OPENAI_API_KEY="test-key", OPENAI_MODEL="gpt-4o-mini")
    @patch("apps.ai.providers.openai_provider._chat")
    def test_openai_difficulty_tagger_when_enabled(self, mock_chat):
        from apps.ai.factory import get_difficulty_tagger
        from apps.ai.providers.openai_provider import OpenAIDifficultyTagger

        mock_chat.return_value = "hard"
        tagger = get_difficulty_tagger()
        assert isinstance(tagger, OpenAIDifficultyTagger)
        assert tagger.tag("A very long and complex calculus proof question", "easy") == "hard"

    @override_settings(AI_ENABLED=True, LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")
    @patch("apps.ai.providers.openai_provider._chat")
    def test_openai_failure_falls_back_in_generator(self, mock_chat):
        from apps.ai.factory import get_question_generator

        mock_chat.return_value = None
        assert get_question_generator().generate(None, "easy", 2) == []

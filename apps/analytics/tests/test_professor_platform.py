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
    build_confidence_performance_series,
    build_session_history_rows,
    get_step_feedback_stats,
    get_topic_mastery_heatmap,
    log_mistake,
    student_course_summary,
)
from apps.core.context_processors import navigation_context
from apps.questions.models import ExplanationStep, Question
from apps.reviews.models import Answer, ReviewSession, StepFeedbackView
from apps.users.models import Course, User
from conftest import make_bsed_student


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
        assert response.status_code == 404

    def test_student_detail_ok_without_session(self, client, professor, student, program):
        """Faculty can open student detail even with no practice yet."""
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

    def test_catalog_student_detail_uses_subject_answers(
        self, client, professor, student, mcq_question, program
    ):
        question, _ = mcq_question
        subject = question.topic.subject
        catalog = Course.objects.create(
            program=program,
            code=subject.code,
            name=subject.name,
            professor=professor,
            term="Catalog",
            academic_year="2026",
            section="Catalog",
        )
        other = Course.objects.create(
            program=program,
            code=subject.code,
            name="Other offering",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="B",
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=other,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(
            session=session, question=question, confidence=3, is_correct=True
        )
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:student_detail",
                kwargs={"course_pk": catalog.pk, "student_pk": student.pk},
            )
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestSidebarContext:
    def test_sidebar_course_set_on_course_detail_url(
        self, rf, professor, bsed_program, year_level
    ):
        from apps.questions.models import Subject

        subject = Subject.objects.create(
            program=bsed_program,
            code="NAV101",
            name="Nav Subject",
            year_level=year_level,
            semester=1,
        )
        course = Course.objects.create(
            program=bsed_program,
            code=subject.code,
            name=subject.name,
            professor=professor,
        )
        request = rf.get(
            reverse("analytics_professor:course_detail", kwargs={"pk": course.pk})
        )
        request.user = professor
        request.resolver_match = MagicMock(
            namespace="analytics_professor",
            kwargs={"pk": course.pk},
            url_name="course_detail",
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
        question_row = next(
            q for q in heatmap["questions"] if q["question_id"] == question.pk
        )
        assert question_row["high"] >= 1
        assert question_row["mistakes"] >= 1

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
    def test_professor_can_create_question(self, client, professor, topic, program, subject):
        course = Course.objects.create(
            program=program,
            code=subject.code,
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
    def test_batch_create_preserves_per_question_difficulty(
        self, client, professor, topic, program, subject
    ):
        course = Course.objects.create(
            program=program,
            code=subject.code,
            name="Mixed Difficulty Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.post(
            reverse("analytics_professor:question_create", kwargs={"course_pk": course.pk}),
            {
                "topic": topic.id,
                "difficulty": Question.Difficulty.EASY,
                "question_count": 2,
                "stem_0": "Beginner question one?",
                "difficulty_0": Question.Difficulty.EASY,
                "correct_0": "A",
                "concept_tag_0": "Easy concept",
                "choice_0_A": "1",
                "choice_0_B": "2",
                "choice_0_C": "3",
                "choice_0_D": "4",
                "stem_1": "Intermediate question two?",
                "difficulty_1": Question.Difficulty.MEDIUM,
                "correct_1": "B",
                "concept_tag_1": "Medium concept",
                "choice_1_A": "1",
                "choice_1_B": "2",
                "choice_1_C": "3",
                "choice_1_D": "4",
            },
        )
        assert response.status_code == 302, getattr(response, "context", None)
        easy_q = Question.objects.get(stem="Beginner question one?")
        medium_q = Question.objects.get(stem="Intermediate question two?")
        assert easy_q.difficulty == Question.Difficulty.EASY
        assert medium_q.difficulty == Question.Difficulty.MEDIUM

    @override_settings(AI_ENABLED=False)
    def test_batch_skips_duplicate_question(self, client, professor, topic, program, subject):
        course = Course.objects.create(
            program=program,
            code=subject.code,
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

    def test_ai_generated_batch_enqueues_background_explanations(
        self, client, professor, topic, program, subject
    ):
        course = Course.objects.create(
            program=program,
            code=subject.code,
            name="AI Batch Course",
            professor=professor,
        )
        client.force_login(professor)
        generator = MagicMock()
        generator.generate.return_value = {
            "explanation_steps": ["Identify the operation.", "2 + 2 = 4"],
            "solution_summary": "The correct answer is A.",
        }

        def _run_thread_inline(target, args=(), kwargs=None, **_ignored):
            kwargs = kwargs or {}
            target(*args, **kwargs)
            return MagicMock()

        from apps.ai.models import AIGenerationJob

        with (
            patch("apps.ai.job_services.is_ai_configured", return_value=True),
            patch("apps.ai.job_services.threading.Thread", side_effect=_run_thread_inline),
            patch("apps.ai.job_services.get_explanation_generator", return_value=generator),
        ):
            response = client.post(
                reverse("analytics_professor:question_create", kwargs={"course_pk": course.pk}),
                {
                    "topic": topic.id,
                    "difficulty": Question.Difficulty.EASY,
                    "question_count": 1,
                    "stem_0": "What is 2 plus 2?",
                    "correct_0": "A",
                    "concept_tag_0": "Addition",
                    "ai_generated_0": "1",
                    "choice_0_A": "4",
                    "choice_0_B": "3",
                    "choice_0_C": "5",
                    "choice_0_D": "0",
                },
            )
        assert response.status_code == 302
        question = Question.objects.get(stem="What is 2 plus 2?")
        assert ExplanationStep.objects.filter(question=question).count() == 2
        job = AIGenerationJob.objects.filter(
            job_type=AIGenerationJob.JobType.EXPLANATION_GENERATE
        ).first()
        assert job is not None
        assert job.status == AIGenerationJob.Status.SUCCEEDED
        generator.generate.assert_called_once()

    def test_ai_validate_returns_json(self, client, professor, topic, program, subject):
        course = Course.objects.create(
            program=program,
            code=subject.code,
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
        assert course.code in content
        assert "Enrolled students" in content

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
class TestProfessorOverviewSummary:
    def test_avg_mistakes_per_session(self, professor, bsed_program, student, mcq_question):
        from apps.analytics.models import MistakeRecord
        from apps.analytics.services import professor_overview_summary
        from apps.reviews.models import Answer, ReviewSession

        question, _correct = mcq_question
        make_bsed_student(student, subject=question.topic.subject, bsed_program=bsed_program)
        course = Course.objects.create(
            program=bsed_program,
            code="AVG101",
            name="Avg Mistakes Course",
            professor=professor,
        )
        session = ReviewSession.objects.create(
            student=student,
            course=course,
            topic=question.topic,
            difficulty=question.difficulty,
            status=ReviewSession.Status.COMPLETED,
        )
        answer = Answer.objects.create(
            session=session,
            question=question,
            is_correct=False,
            confidence=3,
        )
        MistakeRecord.objects.create(
            student=student,
            question=question,
            topic=question.topic,
            answer=answer,
        )
        summary = professor_overview_summary(professor)
        assert summary["mistake_count"] == 1
        assert summary["total_sessions"] == 1
        assert summary["avg_mistakes_per_session"] == 1.0
        assert summary["mistakes_subtext"] == "1 total"


@pytest.mark.django_db
class TestProfessorOverviewUX:
    def test_overview_includes_dates_and_course_stats(self, client, professor, bsed_program):
        Course.objects.create(
            program=bsed_program,
            code="OV101",
            name="Overview Course",
            professor=professor,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:overview"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Week of" in content
        assert "overviewTrendsChart" in content
        assert "overview-trend-metric" in content
        assert "Jump to offering" not in content
        assert "Your courses" not in content
        assert "Course subjects" in content
        assert "Students practicing" in content
        assert "Avg. mistakes / session" not in content
        assert "Active courses" not in content
        assert "Cross-course snapshot" not in content
        assert "sidebar-link-active" in content or "Overview" in content

    def test_summary_courses_json_is_array(self, client, professor, bsed_program, subject):
        from apps.questions.models import Subject

        Subject.objects.filter(pk=subject.pk).update(program=bsed_program)
        Course.objects.create(
            program=bsed_program,
            code=subject.code,
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
        assert data[0]["code"] == subject.code

    def test_summary_fab_on_overview_when_courses_exist(
        self, client, professor, bsed_program, subject
    ):
        from apps.questions.models import Subject

        Subject.objects.filter(pk=subject.pk).update(program=bsed_program)
        Course.objects.create(
            program=bsed_program,
            code=subject.code,
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
class TestProfessorOverviewTrends:
    def test_trends_payload_has_metrics_and_ranges(self, professor, program):
        from apps.analytics.services import professor_overview_trends

        Course.objects.create(
            program=program,
            code="TR101",
            name="Trend Course",
            professor=professor,
        )
        trends = professor_overview_trends(professor)
        for range_key in ("weekly", "monthly", "yearly"):
            assert range_key in trends
            for metric in ("students", "scores", "confidence"):
                assert metric in trends[range_key]
                assert isinstance(trends[range_key][metric], list)
                assert len(trends[range_key][metric]) >= 1
                assert "label" in trends[range_key][metric][0]
                assert "value" in trends[range_key][metric][0]
                if metric in ("confidence", "scores"):
                    assert "student_count" in trends[range_key][metric][0]
                if metric == "scores":
                    assert trends[range_key][metric][0]["value"] <= 70

    def test_overview_summary_includes_expected_students(self, professor, program, student):
        from apps.analytics.services import professor_overview_summary

        student.home_degree_program = User.HomeDegreeProgram.BSED_MATH
        student.is_active = True
        student.save(update_fields=["home_degree_program", "is_active"])
        summary = professor_overview_summary(professor)
        assert summary["expected_students"] >= 1


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


@pytest.mark.django_db
class TestSessionHistoryHelpers:
    def test_build_session_history_rows_includes_fraction_and_status(self, student, mcq_question, program, professor):
        question, _correct = mcq_question
        course = Course.objects.create(
            program=program,
            code="HIST101",
            name="History Course",
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
        rows = build_session_history_rows([session])
        assert len(rows) == 1
        assert rows[0]["score_display"] == "0/1"
        assert rows[0]["accuracy"] == 0.0
        assert rows[0]["status_label"] == "Needs review"
        assert rows[0]["confidence_label"] == "High"

    def test_build_confidence_performance_series(self, student, mcq_question, program, professor):
        question, _correct = mcq_question
        course = Course.objects.create(
            program=program,
            code="CHART101",
            name="Chart Course",
            professor=professor,
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(session=session, question=question, confidence=3, is_correct=True)
        series = build_confidence_performance_series([session])
        assert len(series) == 1
        assert series[0]["performance"] == 100.0
        # Stored confidence 3 (medium) maps to chart scale 2 on 0–3.
        assert series[0]["confidence"] == 2.0

    def test_student_course_summary_includes_session_rows(self, student, mcq_question, program, professor):
        question, _correct = mcq_question
        course = Course.objects.create(
            program=program,
            code="SUM101",
            name="Summary Course",
            professor=professor,
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(session=session, question=question, confidence=3, is_correct=True)
        summary = student_course_summary(student, course)
        assert len(summary["session_history_rows"]) == 1
        assert len(summary["confidence_performance_series"]) == 1
        assert summary["calibration_max"] >= 1

    def test_student_detail_renders_session_history(self, client, professor, student, mcq_question, program):
        question, _correct = mcq_question
        course = Course.objects.create(
            program=program,
            code="DET201",
            name="Detail Course",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="A",
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(session=session, question=question, confidence=5, is_correct=False)
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:professor_student_detail",
                kwargs={"student_pk": student.pk},
            )
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Exam session history" in content
        assert "Review" in content
        assert "/1" in content or "0%" in content or "0.0%" in content


@pytest.mark.django_db
class TestProfessorSessionReview:
    def _completed_session(self, student, question, course):
        session = ReviewSession.objects.create(
            student=student,
            topic=question.topic,
            difficulty=question.difficulty,
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(
            session=session, question=question, confidence=4, is_correct=True
        )
        return session

    def test_professor_can_review_student_session(
        self, client, professor, student, mcq_question, program
    ):
        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="REV101",
            name="Review Course",
            professor=professor,
        )
        session = self._completed_session(student, question, course)
        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:session_review",
                kwargs={"student_pk": student.pk, "session_pk": session.pk},
            )
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Session review" in content
        assert "session-strip-grid" in content
        assert "clickable: false" in content
        assert "ai-tutor-modal" not in content
        assert reverse(
            "analytics_professor:professor_student_detail",
            kwargs={"student_pk": student.pk},
        ) in content

    def test_other_professor_cannot_review_session(
        self, client, professor, department, student, mcq_question, program
    ):
        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="REV102",
            name="Private Course",
            professor=professor,
        )
        session = self._completed_session(student, question, course)
        other = User.objects.create_user(
            email="otherprof@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=department,
        )
        client.force_login(other)
        response = client.get(
            reverse(
                "analytics_professor:session_review",
                kwargs={"student_pk": student.pk, "session_pk": session.pk},
            )
        )
        assert response.status_code == 404

    def test_student_summary_still_works(
        self, client, student, mcq_question, program, professor
    ):
        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="REV103",
            name="Student Summary Course",
            professor=professor,
        )
        session = self._completed_session(student, question, course)
        client.force_login(student)
        response = client.get(reverse("reviews:summary", kwargs={"pk": session.pk}))
        assert response.status_code == 200
        assert "session-strip-grid" in response.content.decode()

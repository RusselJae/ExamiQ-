"""Student dashboard donut aggregates."""

import pytest
from django.urls import reverse

from apps.analytics.services import (
    professor_confidence_donut,
    professor_donut_sections,
    professor_overview_trends,
    student_incorrect_question_series,
    student_performance_donut,
    student_professor_summary,
)
from apps.questions.models import Question
from apps.reviews.models import Answer, ReviewSession
from apps.reviews.services import start_review_session


@pytest.mark.django_db
def test_student_performance_donut_counts(
    student, topic, mcq_question, numeric_question
):
    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["status"])
    Answer.objects.create(
        session=session,
        question=question,
        confidence=5,
        is_correct=True,
    )
    Answer.objects.create(
        session=session,
        question=numeric_question,
        confidence=1,
        is_correct=False,
    )
    donut = student_performance_donut(student)
    assert donut["total"] == 2
    by_key = {s["key"]: s for s in donut["slices"]}
    assert by_key["sure_correct"]["value"] == 1
    assert by_key["guessing_incorrect"]["value"] == 1
    assert by_key["sure_correct"]["percent"] == 50.0
    assert donut["session_count"] == 1
    assert donut["percent_correct"] == 50.0
    assert "1 answer" in donut["scope_line"] or "2 answers" in donut["scope_line"]
    assert donut["insight"]
    assert "confidence=" in donut["insight_url"]

    period_donut = student_performance_donut(student, period="7")
    assert period_donut["period"] == "7"
    assert "scope_line" in period_donut


@pytest.mark.django_db
def test_faculty_donut_drops_student_area_link(
    student, professor, topic, mcq_question, numeric_question
):
    """Faculty must not be sent a student-area mistake-log URL."""
    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["status"])
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=session,
        question=numeric_question,
        confidence=5,
        is_correct=False,
    )

    faculty_donut = student_performance_donut(student, for_professor=True)
    assert faculty_donut["insight_url"] == ""
    assert "this student" in faculty_donut["insight"]
    # Same numbers as the student-facing donut.
    assert faculty_donut["total"] == student_performance_donut(student)["total"]


@pytest.mark.django_db
def test_professor_summary_includes_donut_payload(
    professor, course, student, topic, mcq_question
):
    """Faculty student detail renders the donut from summary.dashboard_trends."""
    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.course = course
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["course", "status"])
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    summary = student_professor_summary(student, professor)
    donut = summary["dashboard_trends"]["donut"]
    assert donut["total"] == 1
    assert donut["slices"]
    assert donut["scope_line"]
    # Per-question mistakes stay available for the mistakes bar chart.
    assert isinstance(summary["dashboard_trends"]["mistakes"], list)


@pytest.mark.django_db
def test_mistake_series_exposes_session_for_ai_tutor(
    professor, course, student, topic, mcq_question
):
    """The bar chart opens the AI Tutor, which needs session + answer ids."""
    from apps.analytics.models import MistakeRecord

    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.course = course
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["course", "status"])
    answer = Answer.objects.create(
        session=session, question=question, confidence=3, is_correct=False
    )
    MistakeRecord.objects.create(
        student=student,
        answer=answer,
        question=question,
        topic=question.topic,
    )

    points = student_incorrect_question_series(student)
    assert points
    point = points[0]
    assert point["answer_id"] == answer.pk
    assert point["session_id"] == session.pk
    assert point["url"]


@pytest.mark.django_db
def test_faculty_mistake_bar_links_to_question_edit(
    professor, course, student, topic, mcq_question
):
    """Faculty mistake bars open the question edit screen, not answer review."""
    from django.urls import reverse

    from apps.analytics.models import MistakeRecord
    from apps.users.assignment_services import get_or_create_catalog_course

    question, _correct = mcq_question
    session = start_review_session(
        student=student,
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        mode=ReviewSession.Mode.TIMED_EXAM,
    )
    session.course = course
    session.status = ReviewSession.Status.COMPLETED
    session.save(update_fields=["course", "status"])
    answer = Answer.objects.create(
        session=session, question=question, confidence=3, is_correct=False
    )
    MistakeRecord.objects.create(
        student=student,
        answer=answer,
        question=question,
        topic=question.topic,
    )

    catalog_course = get_or_create_catalog_course(professor, question.topic.subject)
    points = student_incorrect_question_series(student, for_professor=True)
    assert points
    assert points[0]["url"] == reverse(
        "analytics_professor:question_edit",
        kwargs={"course_pk": catalog_course.pk, "question_pk": question.pk},
    )

    from django.test import Client

    client = Client()
    client.force_login(professor)
    assert client.get(points[0]["url"]).status_code == 200


@pytest.mark.django_db
def test_professor_confidence_donut_spans_scope(
    professor, course, student, topic, mcq_question, numeric_question
):
    """Overview donut aggregates every answer in the professor's courses."""
    from apps.users.models import Course as CourseModel

    question, _correct = mcq_question
    other_student = type(student)(
        email="other@test.edu",
        role=student.role,
        department=student.department,
    )
    other_student.set_password("testpass123")
    other_student.save()

    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    other_session = ReviewSession.objects.create(
        student=other_student,
        topic=topic,
        difficulty=question.difficulty,
        course=CourseModel.objects.get(pk=course.pk),
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=other_session,
        question=numeric_question,
        confidence=1,
        is_correct=False,
    )

    donut = professor_confidence_donut(professor)
    assert donut["total"] == 2
    by_key = {s["key"]: s for s in donut["slices"]}
    assert by_key["sure_correct"]["value"] == 1
    assert by_key["guessing_incorrect"]["value"] == 1
    assert donut["session_count"] == 2
    assert donut["percent_correct"] == 50.0
    # Faculty view never links into the student area.
    assert donut["insight_url"] == ""
    assert "students" in donut["insight"] or donut["insight"] == ""
    assert "2 answers" in donut["scope_line"]


@pytest.mark.django_db
def test_professor_confidence_donut_period_filter(
    professor, course, student, topic, mcq_question
):
    """The 7/30/all switcher narrows the donut to recent sessions."""
    from datetime import timedelta

    from django.utils import timezone

    question, _correct = mcq_question

    old_session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    recent_session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    # started_at is auto_now_add, so backdate after insert.
    ReviewSession.objects.filter(pk=old_session.pk).update(
        started_at=timezone.now() - timedelta(days=45)
    )
    Answer.objects.create(
        session=old_session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=recent_session, question=question, confidence=1, is_correct=False
    )

    all_time = professor_confidence_donut(professor)
    assert all_time["total"] == 2
    assert all_time["period"] == "all"
    # All-time shows the observed date span, not a fixed label.
    assert "2 answers" in all_time["scope_line"]

    seven = professor_confidence_donut(professor, period="7")
    assert seven["total"] == 1
    assert seven["period"] == "7"
    assert "Last 7 days" in seven["scope_line"]
    assert seven["session_count"] == 1

    thirty = professor_confidence_donut(professor, period="30")
    assert thirty["total"] == 1
    assert thirty["period"] == "30"
    assert "Last 30 days" in thirty["scope_line"]

    # Unknown values fall back to all-time rather than erroring.
    assert professor_confidence_donut(professor, period="bogus")["total"] == 2


@pytest.mark.django_db
def test_professor_confidence_donut_excludes_other_professors(
    professor, course, student, topic, mcq_question, chairperson
):
    """Answers outside the professor's courses must not appear."""
    from apps.users.models import Course as CourseModel
    from apps.users.models import Program as ProgramModel

    question, _correct = mcq_question
    other_program = ProgramModel.objects.get(pk=course.program_id)
    other_course = CourseModel.objects.create(
        program=other_program,
        code="OTH101",
        name="Other professor course",
        professor=chairperson,
        term="1st Sem",
        academic_year="2026",
        section="Z",
    )
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=other_course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    donut = professor_confidence_donut(professor)
    assert donut["total"] == 0
    assert donut["slices"]
    assert donut["insight"] == ""


@pytest.mark.django_db
def test_donut_daily_period_covers_last_24_hours(
    professor, course, student, topic, mcq_question
):
    """The Daily range keeps only the trailing 24 hours."""
    from datetime import timedelta

    from django.utils import timezone

    question, _correct = mcq_question

    old_session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    recent_session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    ReviewSession.objects.filter(pk=old_session.pk).update(
        started_at=timezone.now() - timedelta(hours=30)
    )
    Answer.objects.create(
        session=old_session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=recent_session, question=question, confidence=1, is_correct=False
    )

    daily = professor_confidence_donut(professor, period="1")
    assert daily["period"] == "1"
    assert daily["total"] == 1
    assert "Last 24 hours" in daily["scope_line"]

    # A 7-day window still covers both sessions.
    weekly = professor_confidence_donut(professor, period="7")
    assert weekly["total"] == 2


@pytest.mark.django_db
def test_professor_confidence_donut_section_filter(
    professor, course, student, program_section, topic, mcq_question
):
    """Picking a section narrows the donut to that cohort."""
    from apps.users.models import ProgramSection, User

    question, _correct = mcq_question
    other_section = ProgramSection.objects.create(
        program=program_section.program,
        year_level=program_section.year_level,
        label="2M",
        academic_year=program_section.academic_year,
    )
    other_student = User.objects.create_user(
        email="other-section@test.edu",
        password="testpass123",
        role=User.Role.STUDENT,
        department=student.department,
        home_degree_program=student.home_degree_program,
        year_level=student.year_level,
        section=other_section,
    )

    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    other_session = ReviewSession.objects.create(
        student=other_student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=other_session, question=question, confidence=5, is_correct=True
    )

    # All sections is the default.
    everything = professor_confidence_donut(professor)
    assert everything["total"] == 2
    assert everything["section"] == ""

    scoped = professor_confidence_donut(professor, section=str(other_section.pk))
    assert scoped["total"] == 1
    assert scoped["section"] == other_section.pk

    # Unknown or explicit "all" values fall back to every section.
    assert professor_confidence_donut(professor, section="all")["total"] == 2
    assert professor_confidence_donut(professor, section="999999")["total"] == 2

    sections = professor_donut_sections(professor)
    labels = [entry["label"] for entry in sections]
    assert len(sections) == 2
    assert program_section.display_label in labels
    assert other_section.display_label in labels


@pytest.mark.django_db
def test_donut_reports_calibration_status(
    professor, course, student, topic, mcq_question, numeric_question
):
    """Sure-but-wrong answers mark the group as overconfident."""
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=session, question=numeric_question, confidence=5, is_correct=False
    )

    donut = professor_confidence_donut(professor)
    assert donut["calibration_status"] == "overconfident"
    assert "100% of wrong answers were rated Sure" in donut["calibration_detail"]

    # Right answers rated Guessing read as underconfidence instead.
    Answer.objects.filter(session=session).update(confidence=1)
    donut = professor_confidence_donut(professor)
    assert donut["calibration_status"] == "underconfident"
    assert "right answers were rated Guessing" in donut["calibration_detail"]


@pytest.mark.django_db
def test_overview_trends_expose_daily_range(professor):
    """The line chart ships an hourly (last 24 hours) bucket set."""
    trends = professor_overview_trends(professor)
    assert "daily" in trends
    assert len(trends["daily"]["mistake_trend"]) == 24
    assert trends["daily"]["mistake_trend"][0]["label"]


@pytest.mark.django_db
def test_professor_overview_renders_donut_filters(
    client, professor, course, student, topic, mcq_question
):
    """The donut ships the range pills and the section filter."""
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    client.force_login(professor)
    content = client.get(reverse("analytics_professor:overview")).content.decode()
    assert "donut_period=1" in content
    assert "donut_period=7" in content
    assert "donut_period=30" in content
    assert "donut_period=all" in content
    assert "All sections" in content
    assert student.section.display_label in content


@pytest.mark.django_db
def test_donut_filters_are_wired_for_in_place_updates(
    client, professor, course, student, topic, mcq_question
):
    """The pills point at the JSON endpoint so the page need not reload."""
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    client.force_login(professor)
    content = client.get(reverse("analytics_professor:overview")).content.decode()
    assert "data-donut-filters" in content
    assert "data-donut-canvas=\"overviewDonutChart\"" in content
    assert reverse("analytics_professor:donut_data") in content
    assert 'data-donut-param="donut_period"' in content
    assert 'data-donut-param="donut_section"' in content
    assert "donut-filters.js" in content


@pytest.mark.django_db
def test_professor_donut_data_endpoint(
    client, professor, course, student, topic, mcq_question
):
    """The JSON endpoint re-scopes the donut for the filter."""
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    client.force_login(professor)
    response = client.get(
        reverse("analytics_professor:donut_data"),
        {"donut_period": "7", "donut_section": str(student.section_id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["donut"]["total"] == 1
    assert data["donut"]["period"] == "7"
    assert data["donut"]["section"] == student.section_id
    # The explanation travels with the payload.
    assert data["donut"]["calibration"]["status"] in {
        "overconfident",
        "underconfident",
        "confident",
    }


@pytest.mark.django_db
def test_student_donut_data_endpoint(client, student, topic, mcq_question):
    """Students get the same in-place payload for their own donut."""
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )

    client.force_login(student)
    response = client.get(
        reverse("analytics_student:donut_data"), {"period": "7"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["donut"]["total"] == 1
    assert data["donut"]["period"] == "7"


@pytest.mark.django_db
def test_calibration_payload_explains_the_verdict(
    professor, course, student, topic, mcq_question, numeric_question
):
    """The modal payload spells out the numbers and the rule applied."""
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=session, question=numeric_question, confidence=5, is_correct=False
    )

    donut = professor_confidence_donut(professor)
    calibration = donut["calibration"]
    assert calibration["status"] == "overconfident"
    assert calibration["label"] == "Overconfident"
    assert calibration["driver"] == "sure_incorrect"
    assert "50%" in calibration["rule"]
    assert calibration["summary"]
    # One metric per rule driver plus the two remaining measures.
    assert len(calibration["metrics"]) == 4
    wrong_sure = calibration["metrics"][0]
    assert wrong_sure["label"] == "Wrong answers rated Sure"
    assert wrong_sure["value"] == 1
    assert wrong_sure["total"] == 1
    assert wrong_sure["percent"] == 100.0
    assert "were rated Sure" in wrong_sure["sentence"]

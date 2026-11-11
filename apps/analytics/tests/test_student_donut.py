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
from apps.users.models import User


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
def test_professor_donut_only_counts_assigned_students(
    professor, topic, mcq_question, academic_year
):
    """Answers flow to the donut of each student's assigned faculty only."""
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question, _correct = mcq_question
    other_professor = User.objects.create_user(
        email="other.prof@test.edu",
        password="testpass123",
        role=User.Role.PROFESSOR,
        first_name="Other",
        last_name="Prof",
    )
    other_student = User.objects.create_user(
        email="other.student@test.edu",
        password="testpass123",
        role=User.Role.STUDENT,
    )
    first_student = User.objects.create_user(
        email="first.student@test.edu",
        password="testpass123",
        role=User.Role.STUDENT,
    )
    year = AcademicYear.get_current()
    assert year is not None
    subject = question.topic.subject
    me = User.objects.get(pk=professor.pk)
    StudentFacultyAssignment.objects.create(
        student=first_student, faculty=me, subject=subject, academic_year=year
    )
    StudentFacultyAssignment.objects.create(
        student=other_student,
        faculty=other_professor,
        subject=subject,
        academic_year=year,
    )

    for student, confidence, correct in (
        (first_student, 5, True),
        (other_student, 1, False),
    ):
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty="easy",
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(
            session=session,
            question=question,
            confidence=confidence,
            is_correct=correct,
        )

    mine = professor_confidence_donut(me)
    assert mine["total"] == 1
    by_key = {s["key"]: s for s in mine["slices"]}
    assert by_key["sure_correct"]["value"] == 1

    theirs = professor_confidence_donut(other_professor)
    assert theirs["total"] == 1
    theirs_by_key = {s["key"]: s for s in theirs["slices"]}
    assert theirs_by_key["guessing_incorrect"]["value"] == 1

    assert professor_donut_sections(me) == []
    # Sections appear once handled students belong to one. Covered by
    # test_professor_confidence_donut_section_filter.


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
    """Overview donut aggregates answers from the professor's handled students."""
    from apps.users.models import AcademicYear, StudentFacultyAssignment
    from apps.users.models import Course as CourseModel

    question, _correct = mcq_question
    other_student = type(student)(
        email="other@test.edu",
        role=student.role,
        department=student.department,
    )
    other_student.set_password("testpass123")
    other_student.save()

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
    StudentFacultyAssignment.objects.create(
        student=other_student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
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

    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question, _correct = mcq_question

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )

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

    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question, _correct = mcq_question

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )

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
    """Picking a section narrows the donut to that cohort of handled students."""
    from apps.users.models import (
        AcademicYear,
        ProgramSection,
        StudentFacultyAssignment,
        User,
    )

    question, _correct = mcq_question
    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
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
    StudentFacultyAssignment.objects.create(
        student=other_student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
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


@pytest.mark.django_db
def test_professor_confidence_donut_subject_filter(
    professor, course, student, topic, mcq_question, bsed_program, year_level
):
    """The course tab scopes the donut to that handled subject."""
    from apps.questions.models import Question, QuestionChoice, Subject
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question = mcq_question[0]
    other_subject = Subject.objects.create(
        program=topic.subject.program,
        code="TEST-202",
        name="Second Subject",
        year_level=year_level,
        semester=2,
    )
    other_topic = topic.__class__.objects.create(
        subject=other_subject, name="Second Topic"
    )
    other_question = Question.objects.create(
        topic=other_topic,
        difficulty=Question.Difficulty.EASY,
        question_type=Question.QuestionType.MCQ,
        stem="What is 3x + 5 - 2x?",
        status=Question.Status.APPROVED,
    )
    QuestionChoice.objects.create(
        question=other_question, label="A", text="x + 5", is_correct=True
    )
    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=topic.subject,
        academic_year=year,
    )
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=other_subject,
        academic_year=year,
    )

    session = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    other_session = ReviewSession.objects.create(
        student=student,
        topic=other_topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=other_session, question=other_question, confidence=1, is_correct=False
    )

    everything = professor_confidence_donut(professor)
    assert everything["total"] == 2
    assert everything["subject"] == ""

    scoped = professor_confidence_donut(professor, subject=other_subject.pk)
    assert scoped["total"] == 1
    assert scoped["subject"] == other_subject.pk

    # Unknown subject id falls back to everything.
    assert professor_confidence_donut(professor, subject=999999)["total"] == 2


@pytest.mark.django_db
def test_donut_reports_calibration_status(
    professor, course, student, topic, mcq_question, numeric_question
):
    """Sure-but-wrong answers mark the group as overconfident."""
    question, _correct = mcq_question
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
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
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
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
    assert 'id="donut-subject-picker"' in content
    assert 'data-donut-param="donut_subject"' in content
    assert 'id="donut-section-picker"' in content
    assert 'data-donut-param="donut_section"' in content
    assert "All sections" in content


@pytest.mark.django_db
def test_donut_filters_are_wired_for_in_place_updates(
    client, professor, course, student, topic, mcq_question
):
    """The picker and pills point at the JSON endpoint so the page need not reload."""
    question, _correct = mcq_question
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
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
    assert 'data-donut-canvas="overviewDonutChart"' in content
    assert reverse("analytics_professor:donut_data") in content
    assert 'data-donut-param="donut_period"' in content
    assert 'data-donut-param="donut_subject"' in content
    assert 'id="donut-subject-picker"' in content
    assert "donut-filters.js" in content


@pytest.mark.django_db
def test_professor_donut_data_endpoint(
    client, professor, course, student, topic, mcq_question
):
    """The JSON endpoint re-scopes the donut for the filter."""
    question, _correct = mcq_question
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
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
    # Distinct students behind the answers travel with the payload so the
    # "students answered" pill can render beside the calibration badge.
    assert data["donut"]["student_count"] == 1
    # The explanation travels with the payload.
    assert data["donut"]["calibration"]["status"] in {
        "overconfident",
        "underconfident",
        "confident",
    }

    scoped = client.get(
        reverse("analytics_professor:donut_data"),
        {"donut_subject": str(question.topic.subject_id)},
    )
    assert scoped.status_code == 200
    assert scoped.json()["donut"]["total"] == 1
    assert scoped.json()["donut"]["subject"] == question.topic.subject_id


@pytest.mark.django_db
def test_recent_activity_has_one_row_per_student_per_subject(
    professor, course, student, topic, subject, mcq_question
):
    """Rows pair students with courses so the picker filter matches each.

    A student's overall-latest exam lives in BSEM 22 while an older exam
    they completed in BSEM 36 still needs its own visible row when the
    picker narrows to that course.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.services import professor_latest_student_sessions
    from apps.questions.models import Subject, Topic
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question, _correct = mcq_question
    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )

    other_subject = Subject.objects.create(
        program=subject.program,
        code="OTHER-202",
        name="Other Subject",
        year_level=subject.year_level,
        semester=Subject.Semester.FIRST,
    )
    other_topic = Topic.objects.create(
        subject=other_subject,
        name="Other Topic",
    )

    older = ReviewSession.objects.create(
        student=student,
        topic=other_topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
        ended_at=timezone.now() - timedelta(days=3),
    )
    newer = ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
        ended_at=timezone.now() - timedelta(days=1),
    )

    rows = professor_latest_student_sessions(professor)
    assert len(rows) == 2
    by_subject = {row["subject_id"]: row for row in rows}
    assert set(by_subject) == {
        question.topic.subject_id,
        other_topic.subject_id,
    }
    # Newest row first; each row carries its own session's numbers.
    assert rows[0]["latest_session"].pk == newer.pk
    assert rows[1]["latest_session"].pk == older.pk


@pytest.mark.django_db
def test_recent_activity_attributes_session_to_answer_subject(
    professor, course, student, topic, subject, mcq_question
):
    """A session tagged with one topic is attributed to its questions' course.

    The donut scopes answers by ``question__topic__subject``; recent activity
    must match, otherwise legacy sessions tagged with an unrelated topic
    vanish from the course they really belong to.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.services import professor_latest_student_sessions
    from apps.questions.models import Subject, Topic
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question, _correct = mcq_question
    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )

    tagging_subject = Subject.objects.create(
        program=subject.program,
        code="TAG-01",
        name="Tag Subject",
        year_level=subject.year_level,
        semester=Subject.Semester.FIRST,
    )
    unrelated_topic = Topic.objects.create(
        subject=tagging_subject,
        name="Tag Topic",
    )
    session = ReviewSession.objects.create(
        student=student,
        topic=unrelated_topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
        ended_at=timezone.now() - timedelta(days=1),
    )
    answer = Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    del answer

    rows = professor_latest_student_sessions(professor)
    assert len(rows) == 1
    assert rows[0]["subject_id"] == question.topic.subject_id
    assert rows[0]["subject"] == question.topic.subject.code


@pytest.mark.django_db
def test_recent_activity_splits_pooled_session_by_course(
    professor, course, student, topic, subject, mcq_question
):
    """A session pooling several courses contributes a row per course.

    Legacy pooled exams answer questions across many subjects in one
    session; the course picker must still surface each course's own slice
    of scores instead of swallowing them into the dominant course.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.services import professor_latest_student_sessions
    from apps.questions.models import (
        Question,
        QuestionChoice,
        Subject,
        Topic,
    )
    from apps.reviews.models import Answer
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    question, correct_choice = mcq_question
    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )

    pooled_subject = Subject.objects.create(
        program=subject.program,
        code="POOL-02",
        name="Pooled Subject",
        year_level=subject.year_level,
        semester=Subject.Semester.FIRST,
    )
    pooled_topic = Topic.objects.create(
        subject=pooled_subject,
        name="Pooled Topic",
    )

    session = ReviewSession.objects.create(
        student=student,
        topic=pooled_topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
        ended_at=timezone.now() - timedelta(days=1),
    )
    # One completed session pools answers from two different courses.
    second_main = Question.objects.create(
        topic=question.topic,
        difficulty=Question.Difficulty.EASY,
        question_type=Question.QuestionType.MCQ,
        stem="Second main stem.",
        status=Question.Status.APPROVED,
    )
    QuestionChoice.objects.create(
        question=second_main, label="A", text="x", is_correct=True
    )
    Answer.objects.create(
        session=session, question=question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=session, question=second_main, confidence=2, is_correct=False
    )
    pooled_question = Question.objects.create(
        topic=pooled_topic,
        difficulty=Question.Difficulty.EASY,
        question_type=Question.QuestionType.MCQ,
        stem="Pooled stem round to nearest ten.",
        status=Question.Status.APPROVED,
    )
    QuestionChoice.objects.create(
        question=pooled_question, label="A", text="10", is_correct=True
    )
    pooled_question_two = Question.objects.create(
        topic=pooled_topic,
        difficulty=Question.Difficulty.EASY,
        question_type=Question.QuestionType.MCQ,
        stem="Pooled stem alkane formula.",
        status=Question.Status.APPROVED,
    )
    QuestionChoice.objects.create(
        question=pooled_question_two, label="A", text="CH4", is_correct=True
    )
    Answer.objects.create(
        session=session, question=pooled_question, confidence=5, is_correct=True
    )
    Answer.objects.create(
        session=session, question=pooled_question_two, confidence=5, is_correct=True
    )
    del correct_choice

    rows = professor_latest_student_sessions(professor)
    by_subject = {row["subject_id"]: row for row in rows}
    assert set(by_subject) == {
        question.topic.subject_id,
        pooled_subject.pk,
    }
    main = by_subject[question.topic.subject_id]
    assert main["total_questions"] == 2
    assert main["correct_questions"] == 1
    pooled = by_subject[pooled_subject.pk]
    assert pooled["total_questions"] == 2
    assert pooled["correct_questions"] == 2


@pytest.mark.django_db
def test_overview_activity_table_drops_section_and_renames_scores(
    client, professor, course, student, topic, mcq_question
):
    """The Recent activity table shows Student/Subject/Scores columns only."""
    question, _correct = mcq_question
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
    ReviewSession.objects.create(
        student=student,
        topic=topic,
        difficulty=question.difficulty,
        course=course,
        status=ReviewSession.Status.COMPLETED,
    )

    client.force_login(professor)
    content = client.get(reverse("analytics_professor:overview")).content.decode()
    assert ">Scores</th>" in content
    assert ">Course</th>" in content
    assert "Accuracy</th>" not in content
    assert "<th>Section</th>" not in content
    assert 'data-student-id="' in content


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
    response = client.get(reverse("analytics_student:donut_data"), {"period": "7"})
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
    from apps.users.models import AcademicYear, StudentFacultyAssignment

    year = AcademicYear.get_current()
    assert year is not None
    StudentFacultyAssignment.objects.create(
        student=student,
        faculty=professor,
        subject=question.topic.subject,
        academic_year=year,
    )
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

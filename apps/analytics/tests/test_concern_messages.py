"""Tests for threaded mistake concern messages and notifications."""

import pytest
from django.urls import reverse

from apps.analytics.concern_services import (
    concern_needs_faculty_reply,
    concern_thread_for,
    post_concern_message,
    professor_concern_queryset,
)
from apps.analytics.models import MistakeConcernMessage, MistakeRecord
from apps.reviews.models import Answer, ReviewSession
from apps.users.models import Course, Notification


@pytest.fixture
def wrong_answer(db, student, mcq_question):
    question, _correct = mcq_question
    session = ReviewSession.objects.create(
        student=student,
        topic=question.topic,
        difficulty=question.difficulty,
        status=ReviewSession.Status.COMPLETED,
    )
    return Answer.objects.create(
        session=session,
        question=question,
        confidence=1,
        is_correct=False,
    )


@pytest.fixture
def mistake_record(db, wrong_answer):
    from apps.analytics.models import MistakeRecord

    return MistakeRecord.objects.create(
        student=wrong_answer.session.student,
        question=wrong_answer.question,
        topic=wrong_answer.question.topic,
        answer=wrong_answer,
    )


@pytest.mark.django_db
def test_post_concern_message_creates_thread(student, professor, mistake_record):
    msg = post_concern_message(
        mistake_record,
        student,
        body="Why is this wrong?",
    )
    assert msg.pk
    assert MistakeConcernMessage.objects.filter(mistake_record=mistake_record).count() == 1
    assert concern_needs_faculty_reply(mistake_record)

    reply = post_concern_message(
        mistake_record,
        professor,
        body="Check step 2.",
    )
    assert reply.pk
    thread = list(concern_thread_for(mistake_record))
    assert len(thread) == 2
    assert thread[0].body == "Why is this wrong?"
    assert thread[1].body == "Check step 2."
    assert not concern_needs_faculty_reply(mistake_record)


@pytest.mark.django_db
def test_student_message_notifies_professor(student, professor, mistake_record, subject):
    professor.assigned_sections.add(student.section)
    professor.assigned_subjects.add(subject)
    post_concern_message(mistake_record, student, body="Help please")
    assert Notification.objects.filter(
        user=professor,
        read_at__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_student_message_skips_professor_without_subjects(
    student, professor, mistake_record, subject
):
    professor.assigned_sections.add(student.section)
    # Option B: no subjects → no notification
    post_concern_message(mistake_record, student, body="Help please")
    assert not Notification.objects.filter(user=professor).exists()


@pytest.mark.django_db
def test_faculty_reply_notifies_student(student, professor, mistake_record):
    post_concern_message(mistake_record, student, body="Help")
    post_concern_message(mistake_record, professor, body="See step 2")
    assert Notification.objects.filter(
        user=student,
        message__icontains="Faculty replied",
    ).exists()


@pytest.mark.django_db
def test_concern_thread_persists_after_faculty_section_change(
    student, professor, mistake_record, subject, program_section, year_level, program
):
    from apps.users.models import ProgramSection

    professor.assigned_sections.add(student.section)
    professor.assigned_subjects.add(subject)
    post_concern_message(mistake_record, student, body="Need help")
    assert professor_concern_queryset(professor).filter(pk=mistake_record.pk).exists()

    other_section = ProgramSection.objects.create(
        program=program,
        year_level=year_level,
        label="9M",
        academic_year=student.section.academic_year,
        max_students=40,
    )
    professor.assigned_sections.set([other_section])
    assert professor_concern_queryset(professor).filter(pk=mistake_record.pk).exists()
    assert mistake_record.concern_faculty.filter(pk=professor.pk).exists()


@pytest.mark.django_db
def test_upload_concern_view_redirects_to_chat(client, student, wrong_answer):
    from apps.analytics.models import StudentFacultyMessage

    client.force_login(student)
    url = reverse(
        "analytics_student:upload_mistake_concern",
        kwargs={"answer_pk": wrong_answer.pk},
    )
    response = client.post(url, {"body": "I am confused"})
    assert response.status_code == 302
    assert "open_chat=1" in response.url
    assert StudentFacultyMessage.objects.filter(
        conversation__student=student,
        body="I am confused",
    ).exists()


@pytest.mark.django_db
def test_faculty_note_api_appends_reply(client, professor, mistake_record, subject):
    course = Course.objects.create(
        professor=professor,
        program=subject.program,
        code=subject.code,
        name=subject.name,
        section="Catalog",
        term="Catalog",
        academic_year="2025-2026",
    )
    post_concern_message(
        mistake_record,
        mistake_record.student,
        body="Question?",
    )
    client.force_login(professor)
    url = reverse(
        "analytics_professor:feedback_faculty_note",
        kwargs={"course_pk": course.pk, "mistake_pk": mistake_record.pk},
    )
    response = client.post(url, {"faculty_note": "Here is help"})
    assert response.status_code == 200
    assert MistakeConcernMessage.objects.filter(
        mistake_record=mistake_record,
        author=professor,
        body="Here is help",
    ).exists()


@pytest.mark.django_db
def test_faculty_note_api_accepts_image(client, professor, mistake_record, subject):
    from django.core.files.uploadedfile import SimpleUploadedFile

    course = Course.objects.create(
        professor=professor,
        program=subject.program,
        code=subject.code,
        name=subject.name,
        section="Catalog",
        term="Catalog",
        academic_year="2025-2026",
    )
    post_concern_message(mistake_record, mistake_record.student, body="Need help")
    client.force_login(professor)
    url = reverse(
        "analytics_professor:feedback_faculty_note",
        kwargs={"course_pk": course.pk, "mistake_pk": mistake_record.pk},
    )
    image = SimpleUploadedFile(
        "reply.png",
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
        content_type="image/png",
    )
    response = client.post(url, {"faculty_note": "See diagram", "image": image})
    assert response.status_code == 200
    msg = MistakeConcernMessage.objects.filter(
        mistake_record=mistake_record,
        author=professor,
        body="See diagram",
    ).latest("pk")
    assert msg.image
    assert Notification.objects.filter(
        user=mistake_record.student,
        message__icontains="Faculty replied",
    ).exists()


@pytest.mark.django_db
def test_notification_open_marks_read_and_redirects(client, professor, mistake_record):
    note = Notification.objects.create(
        user=professor,
        message="Student asked a question",
        link=f"/feedback/?mistake_id={mistake_record.pk}",
    )
    client.force_login(professor)
    url = reverse("users:notification_open", kwargs={"pk": note.pk})
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"] == note.link
    note.refresh_from_db()
    assert note.is_read


@pytest.mark.django_db
def test_mark_link_clears_student_answer_notifications(client, student, mistake_record):
    link = (
        reverse("analytics_student:mistakes")
        + f"?answer_id={mistake_record.answer_id}&open_tutor=1"
    )
    note = Notification.objects.create(
        user=student,
        message="Faculty replied to your question",
        link=link,
    )
    client.force_login(student)
    url = reverse("users:notifications_mark_link")
    response = client.post(url, {"answer_id": mistake_record.answer_id})
    assert response.status_code == 200
    note.refresh_from_db()
    assert note.is_read


@pytest.mark.django_db
def test_question_list_renders_simplified_filters(client, professor, course):
    client.force_login(professor)
    url = reverse("analytics_professor:question_list", kwargs={"course_pk": course.pk})
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert 'name="topic"' in content
    assert 'name="difficulty"' in content
    assert 'name="active"' in content
    assert 'name="subject"' not in content
    assert 'name="type"' not in content
    assert 'name="date_from"' not in content

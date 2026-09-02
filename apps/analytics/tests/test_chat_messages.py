"""Tests for unified student–faculty chat."""

import pytest
from django.urls import reverse

from apps.analytics.chat_services import (
    chat_needs_faculty_reply,
    get_or_create_conversation,
    post_chat_message,
    professor_chat_queryset,
)
from apps.analytics.models import StudentFacultyMessage
from apps.users.models import Notification, ProgramSection, User


@pytest.mark.django_db
def test_post_chat_message_creates_thread(student, professor, subject):
    professor.assigned_sections.add(student.section)
    professor.assigned_subjects.add(subject)
    conversation = get_or_create_conversation(student)
    msg = post_chat_message(conversation, student, body="Hello faculty")
    assert msg.pk
    assert StudentFacultyMessage.objects.filter(conversation=conversation).count() == 1
    assert chat_needs_faculty_reply(conversation)

    reply = post_chat_message(conversation, professor, body="Hi there")
    assert reply.pk
    assert reply.author_id == professor.pk
    assert not chat_needs_faculty_reply(conversation)


@pytest.mark.django_db
def test_student_message_notifies_professor(student, professor, subject):
    professor.assigned_sections.add(student.section)
    professor.assigned_subjects.add(subject)
    conversation = get_or_create_conversation(student)
    post_chat_message(conversation, student, body="Help please")
    assert Notification.objects.filter(
        user=professor,
        read_at__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_faculty_reply_notifies_student(student, professor):
    conversation = get_or_create_conversation(student)
    post_chat_message(conversation, student, body="Help")
    post_chat_message(conversation, professor, body="See step 2")
    assert Notification.objects.filter(
        user=student,
        message__icontains="Faculty replied",
    ).exists()


@pytest.mark.django_db
def test_chat_thread_persists_after_faculty_section_change(
    student, professor, subject, program_section, year_level, program
):
    professor.assigned_sections.add(student.section)
    professor.assigned_subjects.add(subject)
    conversation = get_or_create_conversation(student)
    post_chat_message(conversation, student, body="Need help")
    assert professor_chat_queryset(professor).filter(pk=conversation.pk).exists()

    other_section = ProgramSection.objects.create(
        program=program,
        year_level=year_level,
        label="9M",
        academic_year=student.section.academic_year,
        max_students=40,
    )
    professor.assigned_sections.set([other_section])
    assert professor_chat_queryset(professor).filter(pk=conversation.pk).exists()
    assert conversation.participating_faculty.filter(pk=professor.pk).exists()


@pytest.mark.django_db
def test_student_chat_api_returns_conversation(client, student):
    conversation = get_or_create_conversation(student)
    post_chat_message(conversation, student, body="Hello")
    client.force_login(student)
    response = client.get(reverse("analytics_student:chat_conversations_api"))
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["conversation_id"] == conversation.pk
    assert data["items"][0]["messages"]


@pytest.mark.django_db
def test_student_chat_message_view(client, student):
    client.force_login(student)
    url = reverse("analytics_student:chat_message")
    response = client.post(url, {"body": "New message"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["item"]["messages"]


@pytest.mark.django_db
def test_professor_chat_conversations_api(client, professor, student, subject):
    professor.assigned_sections.add(student.section)
    professor.assigned_subjects.add(subject)
    conversation = get_or_create_conversation(student)
    post_chat_message(conversation, student, body="Question?")
    client.force_login(professor)
    response = client.get(reverse("analytics_professor:chat_conversations_api"))
    assert response.status_code == 200
    data = response.json()
    assert any(item["student_id"] == student.pk for item in data["items"])


@pytest.mark.django_db
def test_student_dashboard_has_chat_and_tutor_icons(client, student):
    client.force_login(student)
    response = client.get(reverse("analytics_student:dashboard"))
    content = response.content.decode()
    assert 'data-open-chat-modal' in content
    assert 'data-open-ai-tutor' in content
    assert "examiq-chat-modal" in content
    assert "ai-tutor-modal" in content


@pytest.mark.django_db
def test_ai_tutor_modal_has_no_faculty_tab(client, student):
    client.force_login(student)
    response = client.get(reverse("analytics_student:dashboard"))
    content = response.content.decode()
    assert 'data-tutor-screen="faculty"' not in content
    assert "Faculty Conversation" not in content

"""Tests for faculty-to-faculty chat."""

import pytest
from django.urls import reverse

from apps.analytics.faculty_chat_services import (
    faculty_inbox_payload,
    faculty_peers_queryset,
    get_or_create_faculty_conversation,
    post_faculty_message,
)
from apps.analytics.models import FacultyMessage
from apps.users.models import Notification, User


@pytest.fixture
def other_professor(db, department):
    return User.objects.create_user(
        email="prof2@test.edu",
        password="testpass123",
        role=User.Role.PROFESSOR,
        department=department,
        first_name="Other",
        last_name="Prof",
    )


@pytest.mark.django_db
def test_faculty_peers_same_department(professor, other_professor):
    peers = list(faculty_peers_queryset(professor))
    assert other_professor in peers
    assert professor not in peers


@pytest.mark.django_db
def test_post_faculty_message_notifies_peer(professor, other_professor):
    conversation = get_or_create_faculty_conversation(professor, other_professor)
    msg = post_faculty_message(
        conversation, professor, body="Can we sync on exam setup?"
    )
    assert msg.pk
    assert FacultyMessage.objects.filter(conversation=conversation).count() == 1
    assert Notification.objects.filter(
        user=other_professor,
        message__icontains="sent you a message",
    ).exists()


@pytest.mark.django_db
def test_faculty_inbox_includes_peers_without_thread(professor, other_professor):
    payload = faculty_inbox_payload(professor)
    assert any(item.get("peer_id") == other_professor.pk for item in payload["items"])


@pytest.mark.django_db
def test_faculty_chat_conversations_api(client, professor, other_professor):
    conversation = get_or_create_faculty_conversation(professor, other_professor)
    post_faculty_message(conversation, professor, body="Hello peer")
    client.force_login(professor)
    response = client.get(reverse("analytics_professor:faculty_chat_conversations_api"))
    assert response.status_code == 200
    data = response.json()
    assert any(
        item.get("conversation_id") == conversation.pk for item in data["items"]
    )


@pytest.mark.django_db
def test_faculty_chat_message_start(client, professor, other_professor):
    client.force_login(professor)
    url = reverse("analytics_professor:faculty_chat_message_start")
    response = client.post(
        url, {"body": "First message", "peer_id": other_professor.pk}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["item"]["peer_id"] == other_professor.pk
    assert data["item"]["messages"]


@pytest.mark.django_db
def test_overview_chat_modal_has_faculty_tab(client, professor):
    client.force_login(professor)
    response = client.get(reverse("analytics_professor:overview"))
    content = response.content.decode()
    assert 'data-chat-tab="faculty"' in content
    assert 'data-chat-tab="students"' in content
    assert "facultyConversationsUrl" in content

import pytest
from django.db import connection
from django.urls import reverse

from apps.core.models import AuditLog
from apps.questions.models import Question


@pytest.mark.django_db
class TestHealthCheck:
    def test_health_returns_ok(self, client):
        response = client.get(reverse("health"))
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"

    def test_health_checks_database(self):
        connection.ensure_connection()
        assert connection.is_usable()


@pytest.mark.django_db
class TestQuestionToggleActive:
    def test_toggle_deactivates_and_reactivates(self, client, professor, teaching_assignment, mcq_question):
        question, _ = mcq_question
        course = teaching_assignment.course
        client.force_login(professor)
        url = reverse(
            "analytics_professor:question_toggle_active",
            kwargs={"course_pk": course.pk, "question_pk": question.pk},
        )
        assert question.is_active is True
        response = client.post(url)
        assert response.status_code == 302
        question.refresh_from_db()
        assert question.is_active is False
        assert AuditLog.objects.filter(action=AuditLog.Action.QUESTION_TOGGLE).exists()
        client.post(url)
        question.refresh_from_db()
        assert question.is_active is True


@pytest.mark.django_db
class TestAutoApproveQuestions:
    def test_new_question_is_approved(self, client, professor, teaching_assignment, topic):
        course = teaching_assignment.course
        client.force_login(professor)
        url = reverse("analytics_professor:question_create", kwargs={"course_pk": course.pk})
        response = client.post(
            url,
            {
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "question_count": 1,
                "stem_0": "Auto-approved question?",
                "correct_0": "A",
                "choice_0_A": "1",
                "choice_0_B": "2",
                "choice_0_C": "3",
                "choice_0_D": "4",
            },
        )
        assert response.status_code == 302
        question = Question.objects.get(stem="Auto-approved question?")
        assert question.status == Question.Status.APPROVED
        assert AuditLog.objects.filter(action=AuditLog.Action.QUESTION_CREATE).exists()


@pytest.mark.django_db
class TestSetupPreviewAPI:
    def test_preview_returns_question_counts(self, client, student, topic, mcq_question, teaching_assignment):
        client.force_login(student)
        url = reverse("reviews:setup_preview") + f"?topic={topic.pk}"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["easy"] >= 1
        assert "seconds_per_question" in data


@pytest.mark.django_db
class TestAssignmentSectionsAPI:
    def test_sections_api_groups_by_year(
        self, client, chairperson, professor, program_section, subject, program
    ):
        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        from apps.users.models import AcademicTerm

        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            is_current=True,
        )
        client.force_login(chairperson)
        url = (
            reverse("analytics_chairperson:assignment_sections_api")
            + f"?subject={subject.pk}&term={term.pk}"
        )
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data["groups"]) >= 1
        section_ids = [
            s["id"] for group in data["groups"] for s in group["sections"]
        ]
        assert program_section.pk in section_ids


@pytest.mark.django_db
class TestProfessorExamSetupUI:
    def test_exam_setup_renders_card_layout(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        content = response.content.decode()
        assert response.status_code == 200
        assert "exam-setup-grid" in content
        assert "exam-setup-footer" in content
        assert "exam-setup-difficulty-grid" in content


@pytest.mark.django_db
class TestAuditLogging:
    def test_campus_approve_creates_audit_log(self, client, department):
        from django.core import mail
        from apps.users.models import User

        admin = User.objects.create_superuser(
            email="audit-admin@test.edu",
            password="testpass123",
        )
        pending = User.objects.create_user(
            email="audit-pending@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        mail.outbox.clear()
        client.force_login(admin)
        response = client.post(reverse("campus:approve_user", kwargs={"pk": pending.pk}))
        assert response.status_code == 302
        assert AuditLog.objects.filter(
            action=AuditLog.Action.USER_APPROVE,
            target_user=pending,
        ).exists()

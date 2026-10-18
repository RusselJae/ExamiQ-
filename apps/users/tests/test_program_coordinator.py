"""Program coordinator access and management tests."""

import pytest
from django.urls import reverse

from apps.questions.models import Subject
from apps.users.models import Department, Program, User


@pytest.fixture
def coordinator(db, department):
    return User.objects.create_user(
        email="coordinator@test.edu",
        password="testpass123",
        role=User.Role.PROGRAM_COORDINATOR,
        department=department,
    )


@pytest.mark.django_db
class TestProgramCoordinator:
    def test_can_approve_faculty_request_in_own_department(
        self, client, coordinator, department
    ):
        faculty = User.objects.create_user(
            email="pending-faculty@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=department,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )
        client.force_login(coordinator)

        response = client.post(reverse("campus:approve_user", args=[faculty.pk]))

        assert response.status_code == 302
        faculty.refresh_from_db()
        assert faculty.approval_status == User.ApprovalStatus.APPROVED
        assert faculty.is_active is True

    def test_cannot_manage_faculty_request_from_another_department(
        self, client, coordinator
    ):
        other_department = Department.objects.create(name="Other Department")
        faculty = User.objects.create_user(
            email="other-pending-faculty@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=other_department,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )
        client.force_login(coordinator)

        response = client.post(reverse("campus:approve_user", args=[faculty.pk]))

        assert response.status_code == 404
        faculty.refresh_from_db()
        assert faculty.approval_status == User.ApprovalStatus.PENDING

    def test_can_add_subject_only_to_managed_program(
        self, client, coordinator, department, year_level
    ):
        program = Program.objects.create(
            slug="coordinator-test-program",
            name="Coordinator Test Program",
            managing_department=department,
        )
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_list"),
            {
                "program": program.pk,
                "code": "MATH100",
                "name": "Foundations of Mathematics",
                "year_level": year_level.pk,
                "semester": 1,
            },
        )

        assert response.status_code == 302
        assert Subject.objects.filter(program=program, code="MATH100").exists()

    def test_faculty_cannot_open_coordinator_subject_catalog(self, client, professor):
        client.force_login(professor)

        response = client.get(reverse("coordinator:subject_list"))

        assert response.status_code == 403

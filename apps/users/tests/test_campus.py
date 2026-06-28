import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def campus_admin(db):
    return User.objects.create_superuser(
        email="admin@test.edu",
        password="adminpass123!",
    )


@pytest.mark.django_db
class TestCampusPortalAccess:
    def test_non_superuser_gets_403(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("campus:dashboard"))
        assert response.status_code == 403

    def test_superuser_can_view_dashboard(self, client, campus_admin):
        client.force_login(campus_admin)
        response = client.get(reverse("campus:dashboard"))
        assert response.status_code == 200
        assert "Campus Admin" in response.content.decode()

    def test_superuser_can_create_professor(self, client, campus_admin, department):
        client.force_login(campus_admin)
        response = client.post(
            reverse("campus:create_professor"),
            {
                "email": "newprof@test.edu",
                "password": "temppass123!",
                "first_name": "New",
                "last_name": "Professor",
                "department": department.pk,
            },
        )
        assert response.status_code == 302
        user = User.objects.get(email="newprof@test.edu")
        assert user.role == User.Role.PROFESSOR
        assert user.department_id == department.pk

    def test_superuser_can_create_chairperson(self, client, campus_admin, department):
        client.force_login(campus_admin)
        response = client.post(
            reverse("campus:create_chairperson"),
            {
                "email": "newchair@test.edu",
                "password": "temppass123!",
                "first_name": "New",
                "last_name": "Chair",
                "department": department.pk,
            },
        )
        assert response.status_code == 302
        user = User.objects.get(email="newchair@test.edu")
        assert user.role == User.Role.CHAIRPERSON
        assert user.department_id == department.pk

    def test_chairperson_requires_department(self, client, campus_admin):
        client.force_login(campus_admin)
        response = client.post(
            reverse("campus:create_chairperson"),
            {
                "email": "nochair@test.edu",
                "password": "temppass123!",
                "first_name": "No",
                "last_name": "Dept",
                "department": "",
            },
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="nochair@test.edu").exists()

    def test_superuser_can_approve_pending_user(self, client, campus_admin, department):
        pending = User.objects.create_user(
            email="pending@test.edu",
            password="temppass123!",
            role=User.Role.PROFESSOR,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        client.force_login(campus_admin)
        response = client.post(reverse("campus:approve_user", kwargs={"pk": pending.pk}))
        assert response.status_code == 302
        pending.refresh_from_db()
        assert pending.is_active is True
        assert pending.approval_status == User.ApprovalStatus.APPROVED

    def test_superuser_can_reject_pending_user(self, client, campus_admin, department):
        pending = User.objects.create_user(
            email="reject@test.edu",
            password="temppass123!",
            role=User.Role.CHAIRPERSON,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        client.force_login(campus_admin)
        response = client.post(reverse("campus:reject_user", kwargs={"pk": pending.pk}))
        assert response.status_code == 302
        pending.refresh_from_db()
        assert pending.is_active is False
        assert pending.approval_status == User.ApprovalStatus.REJECTED


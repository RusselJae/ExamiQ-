import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestRoleAccess:
    def test_student_cannot_access_professor_dashboard(self, client, student):
        client.force_login(student)
        response = client.get(reverse("analytics_professor:dashboard"))
        assert response.status_code == 403

    def test_professor_cannot_access_campus_admin_index_as_staff_only(self, client, professor):
        client.force_login(professor)
        response = client.get(reverse("admin:index"))
        # Faculty are not staff; Django admin redirects or forbids.
        assert response.status_code in (302, 403)

    def test_student_can_access_own_dashboard(self, client, student):
        client.force_login(student)
        response = client.get(reverse("analytics_student:dashboard"))
        assert response.status_code == 200

    def test_chairperson_can_access_dashboard(self, client, chairperson):
        client.force_login(chairperson)
        response = client.get(reverse("analytics_chairperson:dashboard"))
        assert response.status_code == 200

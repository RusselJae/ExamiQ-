import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.filtering import redirect_preserving_filters
from apps.users.models import User


@pytest.mark.django_db
class TestRedirectPreservingFilters:
    def test_keeps_query_string_from_matching_referer(self):
        factory = RequestFactory()
        list_url = reverse("campus:user_list")
        request = factory.post(
            reverse("campus:approve_user", kwargs={"pk": 1}),
            HTTP_REFERER=f"http://testserver{list_url}?role=professor&status=pending",
        )
        request.get_host = lambda: "testserver"
        response = redirect_preserving_filters(request, "campus:user_list")
        assert response.status_code == 302
        assert response.url == f"{list_url}?role=professor&status=pending"

    def test_falls_back_without_referer(self):
        factory = RequestFactory()
        request = factory.post(reverse("campus:user_list"))
        request.get_host = lambda: "testserver"
        response = redirect_preserving_filters(request, "campus:user_list")
        assert response.status_code == 302
        assert response.url == reverse("campus:user_list")

    def test_ignores_external_referer(self):
        factory = RequestFactory()
        request = factory.post(
            reverse("campus:user_list"),
            HTTP_REFERER="https://evil.example/campus/users/?role=student",
        )
        request.get_host = lambda: "testserver"
        response = redirect_preserving_filters(request, "campus:user_list")
        assert response.url == reverse("campus:user_list")


@pytest.mark.django_db
class TestPaginationQuerystring:
    def test_next_link_uses_single_question_mark(self, client):
        admin = User.objects.create_superuser(
            email="pager-admin@test.edu",
            password="testpass123",
        )
        for i in range(30):
            User.objects.create_user(
                email=f"pager{i}@test.edu",
                password="testpass123",
                role=User.Role.STUDENT,
            )
        client.force_login(admin)
        response = client.get(reverse("campus:user_list"), {"role": "student"})
        content = response.content.decode()
        assert response.status_code == 200
        assert 'href="??' not in content
        assert "page=2" in content
        assert "role=student" in content.replace("&amp;", "&")


@pytest.mark.django_db
class TestCampusFiltersPersistOnRowAction:
    def test_approve_preserves_filters(self, client, department):
        admin = User.objects.create_superuser(
            email="filter-admin@test.edu",
            password="testpass123",
        )
        pending = User.objects.create_user(
            email="filter-pending@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        client.force_login(admin)
        list_url = reverse("campus:user_list")
        response = client.post(
            reverse("campus:approve_user", kwargs={"pk": pending.pk}),
            HTTP_REFERER=f"http://testserver{list_url}?role=professor&status=pending",
        )
        assert response.status_code == 302
        assert "role=professor" in response.url
        assert "status=pending" in response.url

    def test_remove_filters_button_appears_when_active(self, client):
        admin = User.objects.create_superuser(
            email="remove-filter-admin@test.edu",
            password="testpass123",
        )
        client.force_login(admin)
        response = client.get(reverse("campus:user_list"), {"role": "student"})
        content = response.content.decode()
        assert "Remove filters" in content
        assert reverse("campus:user_list") in content

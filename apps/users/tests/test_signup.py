import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestSignupRoles:
    def test_public_signup_always_creates_student(self, client):
        response = client.post(
            reverse("account_signup"),
            {
                "email": "newstudent@test.edu",
                "password1": "strongpass123!",
                "password2": "strongpass123!",
            },
        )
        assert response.status_code == 302
        user = User.objects.get(email="newstudent@test.edu")
        assert user.role == User.Role.STUDENT

import pytest
from django.urls import reverse

from apps.reviews.exam_setup_services import get_or_create_exam_setup
from apps.reviews.models import ExamSetup


@pytest.mark.django_db
class TestExamSetupViews:
    def test_professor_can_edit_exam_setup(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "Manage Exam Setup" in response.content.decode()

    def test_exam_setup_auto_created_with_assignment(self, teaching_assignment):
        setup = get_or_create_exam_setup(teaching_assignment.course)
        assert setup.is_enabled is True
        assert setup.allowed_difficulties

    def test_professor_can_disable_exam_setup(self, client, professor, teaching_assignment):
        course = teaching_assignment.course
        setup = get_or_create_exam_setup(course)
        client.force_login(professor)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.post(
            url,
            {
                "is_enabled": "",
                "allowed_difficulties": setup.effective_difficulties(),
            },
        )
        assert response.status_code == 302
        setup.refresh_from_db()
        assert setup.is_enabled is False

    def test_other_professor_cannot_access_exam_setup(
        self, client, professor, chairperson, program, teaching_assignment
    ):
        other = chairperson
        course = teaching_assignment.course
        client.force_login(other)
        url = reverse("analytics_professor:exam_setup", kwargs={"course_pk": course.pk})
        response = client.get(url)
        assert response.status_code in (403, 404)

"""Program coordinator access and management tests."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.questions.models import Subject
from apps.users.models import Department, Program, User


def _png_upload(name: str = "banner.png") -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (20, 65, 46)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


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

    def test_subject_banner_defaults_to_a_course_asset(
        self, client, coordinator, department, year_level
    ):
        program = Program.objects.create(
            slug="coordinator-banner-default-program",
            name="Coordinator Banner Program",
            managing_department=department,
        )
        subject = Subject.objects.create(
            program=program,
            year_level=year_level,
            semester=Subject.Semester.FIRST,
            code="MATH300",
            name="Default Banner Course",
        )

        assert subject.banner_url.startswith("/static/assets/course_bg")
        assert subject.banner_url.endswith(".jpg")
        assert subject.banner_position in Subject.BANNER_POSITIONS

    def test_add_subject_with_banner_stores_upload(
        self, client, coordinator, department, year_level, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        program = Program.objects.create(
            slug="coordinator-banner-upload-program",
            name="Coordinator Banner Upload Program",
            managing_department=department,
        )
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_list"),
            {
                "code": "MATH301",
                "name": "Custom Banner Course",
                "year_level": year_level.pk,
                "semester": 1,
                "banner": _png_upload(),
            },
        )

        assert response.status_code == 302
        subject = Subject.objects.get(program=program, code="MATH301")
        assert subject.banner
        assert subject.banner_url == subject.banner.url
        assert subject.banner_url.startswith(settings.MEDIA_URL)
        assert subject.banner_url.endswith("banner.png")

    def test_subject_catalog_has_edit_and_delete_actions(
        self, client, coordinator, department, year_level
    ):
        program = Program.objects.create(
            slug="coordinator-actions-program",
            name="Coordinator Actions Program",
            managing_department=department,
        )
        subject = Subject.objects.create(
            program=program,
            year_level=year_level,
            semester=Subject.Semester.FIRST,
            code="MATH200",
            name="Advanced Mathematics",
        )
        client.force_login(coordinator)

        content = client.get(reverse("coordinator:subject_list")).content.decode()

        assert reverse("coordinator:subject_edit", args=[subject.pk]) in content
        assert reverse("coordinator:subject_delete", args=[subject.pk]) in content
        # Add course form lives in a dialog, not a side panel.
        assert 'id="add-course-dialog"' in content
        assert 'id="edit-course-dialog"' in content
        assert "data-open-course-dialog" in content
        assert "data-edit-course" in content
        # Search + filter controls and the stat columns.
        assert 'name="q"' in content
        assert "Faculty" in content
        assert "Questions" in content
        assert "Materials" in content

    def test_can_edit_subject_in_managed_program(
        self, client, coordinator, department, year_level
    ):
        program = Program.objects.create(
            slug="coordinator-edit-program",
            name="Coordinator Edit Program",
            managing_department=department,
        )
        subject = Subject.objects.create(
            program=program,
            year_level=year_level,
            semester=Subject.Semester.FIRST,
            code="MATH201",
            name="Linear Algebra",
        )
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_edit", args=[subject.pk]),
            {
                "program": program.pk,
                "code": "MATH202",
                "name": "Abstract Algebra",
                "year_level": year_level.pk,
                "semester": Subject.Semester.SECOND,
            },
        )

        assert response.status_code == 302
        subject.refresh_from_db()
        assert subject.code == "MATH202"
        assert subject.name == "Abstract Algebra"
        assert subject.semester == Subject.Semester.SECOND

    def test_cannot_edit_subject_from_another_department(
        self, client, coordinator, year_level
    ):
        other_department = Department.objects.create(name="Other Department")
        other_program = Program.objects.create(
            slug="coordinator-other-program",
            name="Other Program",
            managing_department=other_department,
        )
        subject = Subject.objects.create(
            program=other_program,
            year_level=year_level,
            semester=Subject.Semester.FIRST,
            code="OTHER200",
            name="Other Subject",
        )
        client.force_login(coordinator)

        response = client.get(reverse("coordinator:subject_edit", args=[subject.pk]))

        assert response.status_code == 404

    def test_can_delete_subject_in_managed_program(
        self, client, coordinator, department, year_level
    ):
        program = Program.objects.create(
            slug="coordinator-delete-program",
            name="Coordinator Delete Program",
            managing_department=department,
        )
        subject = Subject.objects.create(
            program=program,
            year_level=year_level,
            semester=Subject.Semester.FIRST,
            code="MATH203",
            name="Discrete Mathematics",
        )
        client.force_login(coordinator)

        response = client.post(reverse("coordinator:subject_delete", args=[subject.pk]))

        assert response.status_code == 302
        assert not Subject.objects.filter(pk=subject.pk).exists()

    def test_cannot_delete_subject_from_another_department(
        self, client, coordinator, year_level
    ):
        other_department = Department.objects.create(name="Another Department")
        other_program = Program.objects.create(
            slug="coordinator-other-delete-program",
            name="Other Delete Program",
            managing_department=other_department,
        )
        subject = Subject.objects.create(
            program=other_program,
            year_level=year_level,
            semester=Subject.Semester.FIRST,
            code="OTHER201",
            name="Other Delete Subject",
        )
        client.force_login(coordinator)

        response = client.post(reverse("coordinator:subject_delete", args=[subject.pk]))

        assert response.status_code == 404
        assert Subject.objects.filter(pk=subject.pk).exists()

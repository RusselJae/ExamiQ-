"""Chairperson dedicated screens: accounts, subjects, dashboard."""

import pytest
from django.urls import reverse

from apps.questions.models import Subject
from apps.users.models import Department, Program, User


@pytest.fixture
def chair_department(db):
    return Department.objects.create(name="Chair Test Department")


@pytest.fixture
def chairperson(db, chair_department):
    return User.objects.create_user(
        email="chairportal@test.edu",
        password="testpass123",
        role=User.Role.CHAIRPERSON,
        department=chair_department,
    )


@pytest.fixture
def chair_program(db, chair_department, year_level):
    return Program.objects.create(
        slug="chair-test-program",
        name="Chair Test Program",
        managing_department=chair_department,
    )


@pytest.mark.django_db
class TestChairpersonAccounts:
    def test_lists_and_approves_department_faculty(
        self, client, chairperson, chair_department
    ):
        faculty = User.objects.create_user(
            email="chair-pending@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=chair_department,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )
        client.force_login(chairperson)

        assert client.get(reverse("analytics_chairperson:accounts")).status_code == 200

        response = client.post(
            reverse("analytics_chairperson:account_approve", args=[faculty.pk])
        )
        assert response.status_code == 302
        faculty.refresh_from_db()
        assert faculty.approval_status == User.ApprovalStatus.APPROVED
        assert faculty.is_active is True

    def test_rejects_pending_faculty(self, client, chairperson, chair_department):
        faculty = User.objects.create_user(
            email="chair-reject@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=chair_department,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )
        client.force_login(chairperson)
        response = client.post(
            reverse("analytics_chairperson:account_reject", args=[faculty.pk])
        )
        assert response.status_code == 302
        faculty.refresh_from_db()
        assert faculty.approval_status == User.ApprovalStatus.REJECTED

    def test_cannot_touch_other_department_faculty(self, client, chairperson):
        other = Department.objects.create(name="Far Department")
        faculty = User.objects.create_user(
            email="far-faculty@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=other,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )
        client.force_login(chairperson)
        response = client.post(
            reverse("analytics_chairperson:account_approve", args=[faculty.pk])
        )
        assert response.status_code == 404
        faculty.refresh_from_db()
        assert faculty.approval_status == User.ApprovalStatus.PENDING

    def test_professor_cannot_open_accounts(self, client, professor):
        client.force_login(professor)
        assert client.get(reverse("analytics_chairperson:accounts")).status_code == 403

    def test_active_users_listed_as_approved_with_toggle(
        self, client, chairperson, chair_department
    ):
        faculty = User.objects.create_user(
            email="active-faculty@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=chair_department,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
        )
        client.force_login(chairperson)
        content = client.get(reverse("analytics_chairperson:accounts")).content.decode()
        assert "active-faculty@test.edu" in content
        assert "Approved" in content

        response = client.post(
            reverse("analytics_chairperson:account_toggle_active", args=[faculty.pk])
        )
        assert response.status_code == 302
        faculty.refresh_from_db()
        assert faculty.is_active is False

        response = client.post(
            reverse("analytics_chairperson:account_toggle_active", args=[faculty.pk])
        )
        assert response.status_code == 302
        faculty.refresh_from_db()
        assert faculty.is_active is True

    def test_can_deactivate_and_archive_student(
        self, client, program_section
    ):
        edu, _ = Department.objects.get_or_create(name="College of Education")
        chairperson = User.objects.create_user(
            email="edu-chair@test.edu",
            password="testpass123",
            role=User.Role.CHAIRPERSON,
            department=edu,
        )
        student = User.objects.create_user(
            email="chair-student@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
            department=edu,
            home_degree_program=User.HomeDegreeProgram.BSED_MATH,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
            section=program_section,
            year_level=program_section.year_level,
        )
        client.force_login(chairperson)
        content = client.get(reverse("analytics_chairperson:accounts")).content.decode()
        assert "chair-student@test.edu" in content
        assert "Deactivate" in content
        assert "Archive" in content
        assert program_section.display_label in content

        response = client.post(
            reverse("analytics_chairperson:account_toggle_active", args=[student.pk])
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.is_active is False

        response = client.post(
            reverse("analytics_chairperson:account_archive", args=[student.pk])
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.is_archived is True
        assert student.is_active is False

        archived_page = client.get(
            reverse("analytics_chairperson:accounts"), {"active": "archived"}
        )
        assert "chair-student@test.edu" in archived_page.content.decode()
        assert "Archived" in archived_page.content.decode()

        response = client.post(
            reverse("analytics_chairperson:account_restore", args=[student.pk])
        )
        assert response.status_code == 302
        student.refresh_from_db()
        assert student.is_archived is False
        assert student.is_active is True

    def test_accounts_list_shows_faculty_section_labels(
        self,
        client,
        chairperson,
        chair_department,
        chair_program,
        year_level,
        academic_year,
        academic_term,
    ):
        from apps.questions.models import Subject
        from apps.users.models import ProgramSection, TeachingAssignment

        section = ProgramSection.objects.create(
            program=chair_program,
            year_level=year_level,
            label="1A",
            academic_year=academic_year,
            is_active=True,
        )
        subject = Subject.objects.create(
            program=chair_program,
            code="CHAIR-SEC",
            name="Chair Section Subject",
            year_level=year_level,
            semester=1,
        )
        faculty = User.objects.create_user(
            email="assigned-faculty@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=chair_department,
            approval_status=User.ApprovalStatus.APPROVED,
            is_active=True,
        )
        TeachingAssignment.objects.create(
            professor=faculty,
            program_section=section,
            subject=subject,
            term=academic_term,
            assigned_by=chairperson,
        )
        client.force_login(chairperson)
        content = client.get(reverse("analytics_chairperson:accounts")).content.decode()
        assert faculty.email in content
        assert section.display_label in content


@pytest.mark.django_db
class TestChairpersonSubjects:
    def test_add_edit_remove_subject(
        self, client, chairperson, chair_program, year_level
    ):
        client.force_login(chairperson)

        response = client.get(reverse("analytics_chairperson:subjects"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "lg:grid-cols-[minmax(0,1fr)_22rem]" in content
        assert "min-w-[40rem]" in content

        response = client.post(
            reverse("analytics_chairperson:subjects"),
            {
                "program": chair_program.pk,
                "code": "MATH200",
                "name": "Chair Subject",
                "year_level": year_level.pk,
                "semester": 1,
            },
        )
        assert response.status_code == 302
        subject = Subject.objects.get(program=chair_program, code="MATH200")

        response = client.post(
            reverse("analytics_chairperson:subject_edit", args=[subject.pk]),
            {
                "program": chair_program.pk,
                "code": "MATH200",
                "name": "Chair Subject Renamed",
                "year_level": year_level.pk,
                "semester": 2,
            },
        )
        assert response.status_code == 302
        subject.refresh_from_db()
        assert subject.name == "Chair Subject Renamed"
        assert subject.semester == 2

        response = client.post(
            reverse("analytics_chairperson:subject_delete", args=[subject.pk])
        )
        assert response.status_code == 302
        assert not Subject.objects.filter(pk=subject.pk).exists()

    def test_cannot_manage_other_department_subject(
        self, client, chairperson, year_level
    ):
        other_dept = Department.objects.create(name="Other Dept")
        other_program = Program.objects.create(
            slug="other-program",
            name="Other Program",
            managing_department=other_dept,
        )
        subject = Subject.objects.create(
            program=other_program,
            code="OTHER100",
            name="Other Subject",
            year_level=year_level,
            semester=1,
        )
        client.force_login(chairperson)
        assert (
            client.get(
                reverse("analytics_chairperson:subject_edit", args=[subject.pk])
            ).status_code
            == 404
        )
        assert (
            client.post(
                reverse("analytics_chairperson:subject_delete", args=[subject.pk])
            ).status_code
            == 404
        )
        assert Subject.objects.filter(pk=subject.pk).exists()

    def test_faculty_cannot_open_subject_management(self, client, professor):
        client.force_login(professor)
        assert client.get(reverse("analytics_chairperson:subjects")).status_code == 403


@pytest.mark.django_db
class TestChairpersonDashboard:
    def test_dashboard_shows_management_shortcuts(self, client, chairperson):
        client.force_login(chairperson)
        response = client.get(reverse("analytics_chairperson:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Manage your department" in content
        assert reverse("analytics_chairperson:accounts") in content
        assert reverse("analytics_chairperson:subjects") in content
        assert reverse("analytics_chairperson:assignments") in content

    def test_dashboard_hides_program_analytics_and_course_audit(
        self, client, chairperson
    ):
        """Both were dropped from the coordinator sidebar."""
        client.force_login(chairperson)
        content = client.get(
            reverse("analytics_chairperson:dashboard")
        ).content.decode()
        program_analytics = reverse("analytics_chairperson:analytics_by_program")
        course_audit = reverse("analytics_chairperson:course_audit")
        assert f'href="{program_analytics}"' not in content
        assert f'href="{course_audit}"' not in content

    def test_dashboard_hides_retired_panels(self, client, chairperson):
        client.force_login(chairperson)
        content = client.get(
            reverse("analytics_chairperson:dashboard")
        ).content.decode()
        assert "Degree programs" not in content
        assert "With activity" not in content
        assert "All degree programs" not in content
        assert "Total sessions" not in content
        assert "Total answers" not in content
        assert "Most sessions" not in content
        assert "data-sessions" not in content

"""Program Coordinator role test cases.

Maps to the manual test-case table ``docs/role-test-cases.md`` (Appendix A.3),
rows TC-C01 to TC-C07:

* TC-C01 Sign In
* TC-C02 Coordinator dashboard
* TC-C03 Subject catalog — list and create
* TC-C04 Subject catalog — edit
* TC-C05 Subject catalog — delete
* TC-C06 User account management
* TC-C07 Program sections and teaching assignments

The coordinator console is mounted under ``/coordinator/`` and is scoped to the
programs managed by the coordinator's own department.
"""

import pytest
from django.urls import reverse

from apps.questions.models import Subject
from apps.users.models import (
    Course,
    Department,
    Program,
    ProgramSection,
    TeachingAssignment,
    User,
)


@pytest.fixture
def managed_program(db, coordinator):
    """Program whose managing department is the coordinator's department."""
    return Program.objects.create(
        slug="coordinator-program",
        name="Coordinator Program",
        managing_department=coordinator.department,
    )


@pytest.fixture
def managed_subject(db, managed_program, year_level):
    return Subject.objects.create(
        program=managed_program,
        year_level=year_level,
        semester=Subject.Semester.FIRST,
        code="COORD101",
        name="Coordinator Course",
    )


@pytest.fixture
def managed_section(db, managed_program, year_level, academic_year):
    return ProgramSection.objects.create(
        program=managed_program,
        year_level=year_level,
        label="1",
        academic_year=academic_year,
        max_students=40,
    )


@pytest.fixture
def other_department(db):
    return Department.objects.create(name="Unmanaged Department")


@pytest.fixture
def managed_student(db, coordinator, managed_program, year_level):
    """Student whose home degree program is managed by the coordinator."""
    return User.objects.create_user(
        email="managed.student@test.edu",
        password="testpass123",
        role=User.Role.STUDENT,
        department=coordinator.department,
        home_degree_program=managed_program.slug,
        year_level=year_level,
    )


@pytest.mark.django_db
class TestCoordinatorSignIn:
    """TC-C01 — Sign in and role-based landing."""

    def test_coordinator_sign_in_redirects_to_the_coordinator_console(
        self, client, coordinator, settings
    ):
        settings.LOGIN_OTP_EXEMPT_EMAILS = {coordinator.email}

        response = client.post(
            reverse("account_login"),
            {"login": coordinator.email, "password": "testpass123"},
        )

        assert response.status_code == 302
        assert response.url == reverse("campus:dashboard")

    def test_coordinator_cannot_open_the_faculty_console(self, client, coordinator):
        """Actual error: role mismatch."""
        client.force_login(coordinator)

        response = client.get(reverse("analytics_professor:course_list"))

        assert response.status_code == 403

    def test_chairperson_cannot_open_the_coordinator_console(self, client, chairperson):
        """Actual error: role mismatch."""
        client.force_login(chairperson)

        response = client.get(reverse("campus:dashboard"))

        assert response.status_code == 403


@pytest.mark.django_db
class TestCoordinatorDashboard:
    """TC-C02 — Coordinator dashboard."""

    def test_dashboard_renders_with_scope_counts(self, client, coordinator, student):
        client.force_login(coordinator)

        response = client.get(reverse("campus:dashboard"))

        assert response.status_code == 200
        assert "student_count" in response.context
        assert "professor_count" in response.context
        assert "pending_count" in response.context

    def test_dashboard_lists_only_managed_programs_sections(
        self, client, coordinator, managed_section, program_section
    ):
        client.force_login(coordinator)

        response = client.get(reverse("campus:dashboard"))

        assert response.status_code == 200
        assert response.context["section_count"] == 1


@pytest.mark.django_db
class TestCoordinatorSubjectCatalog:
    """TC-C03 — Subject catalog listing and creation."""

    def test_subject_list_shows_managed_subjects(
        self, client, coordinator, managed_subject
    ):
        client.force_login(coordinator)

        response = client.get(reverse("coordinator:subject_list"))

        assert response.status_code == 200
        assert managed_subject in list(response.context["subjects"])
        # Stat columns are attached for the table.
        subject = next(
            s for s in response.context["subjects"] if s.pk == managed_subject.pk
        )
        assert subject.faculty_count == 0
        assert subject.student_count == 0
        assert subject.question_count == 0
        assert subject.material_count == 0

    def test_subject_list_filters_by_search_and_program(
        self, client, coordinator, managed_program, managed_subject, year_level
    ):
        from apps.questions.models import Subject

        other = Subject.objects.create(
            program=managed_program,
            code="MATH999",
            name="Unrelated Topic",
            year_level=year_level,
            semester=Subject.Semester.FIRST,
        )
        client.force_login(coordinator)

        response = client.get(
            reverse("coordinator:subject_list"), {"q": managed_subject.code}
        )

        assert response.status_code == 200
        assert managed_subject in list(response.context["subjects"])
        assert other not in list(response.context["subjects"])
        assert response.context["search_query"] == managed_subject.code
        assert response.context["filter_has_active"] is True

    def test_subject_list_hides_subjects_of_other_departments(
        self, client, coordinator, subject
    ):
        client.force_login(coordinator)

        response = client.get(reverse("coordinator:subject_list"))

        assert response.status_code == 200
        assert subject not in list(response.context["subjects"])

    def test_create_subject_adds_it_to_the_catalog(
        self, client, coordinator, managed_program, year_level
    ):
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_list"),
            {
                "program": managed_program.pk,
                "code": "MATH201",
                "name": "Linear Algebra",
                "year_level": year_level.pk,
                "semester": 1,
            },
        )

        assert response.status_code == 302
        created = Subject.objects.get(program=managed_program, code="MATH201")
        assert created.name == "Linear Algebra"
        assert Course.objects.filter(
            program=managed_program,
            code="MATH201",
            term="Catalog",
            section="Catalog",
        ).exists()

    def test_create_subject_rejects_a_duplicate_code(
        self, client, coordinator, managed_program, managed_subject, year_level
    ):
        """Actual error: duplicate course code for the same program."""
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_list"),
            {
                "program": managed_program.pk,
                "code": managed_subject.code,
                "name": "Duplicate Course",
                "year_level": year_level.pk,
                "semester": 1,
            },
        )

        assert response.status_code == 200
        assert (
            f"Course code {managed_subject.code} already exists for this program."
            in response.content.decode()
        )
        assert (
            Subject.objects.filter(
                program=managed_program, code=managed_subject.code
            ).count()
            == 1
        )

    def test_faculty_cannot_open_the_subject_catalog(self, client, professor):
        """Actual error: role mismatch."""
        client.force_login(professor)

        response = client.get(reverse("coordinator:subject_list"))

        assert response.status_code == 403


@pytest.mark.django_db
class TestCoordinatorEditSubject:
    """TC-C04 — Edit a catalog subject."""

    def test_edit_subject_updates_the_record(
        self, client, coordinator, managed_subject, year_level
    ):
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_edit", args=[managed_subject.pk]),
            {
                "program": managed_subject.program_id,
                "code": "COORD102",
                "name": "Renamed Course",
                "year_level": year_level.pk,
                "semester": 2,
            },
        )

        assert response.status_code == 302
        managed_subject.refresh_from_db()
        assert managed_subject.code == "COORD102"
        assert managed_subject.name == "Renamed Course"
        assert managed_subject.semester == 2

    def test_cannot_edit_a_subject_of_another_department(
        self, client, coordinator, subject
    ):
        """Actual error: subject outside the managed programs."""
        client.force_login(coordinator)

        response = client.get(reverse("coordinator:subject_edit", args=[subject.pk]))

        assert response.status_code == 404

    def test_cannot_move_a_subject_into_another_program(
        self, client, coordinator, managed_subject, program, year_level
    ):
        """Program is not editable: posted program values are ignored."""
        client.force_login(coordinator)
        managed_subject_original_program_id = managed_subject.program_id

        response = client.post(
            reverse("coordinator:subject_edit", args=[managed_subject.pk]),
            {
                "program": program.pk,
                "code": managed_subject.code,
                "name": managed_subject.name,
                "year_level": year_level.pk,
                "semester": 1,
            },
        )

        assert response.status_code == 302
        managed_subject.refresh_from_db()
        # The subject keeps the program it was created with — the posted
        # "program" value is ignored since the field is not editable.
        assert managed_subject.program_id == managed_subject_original_program_id


@pytest.mark.django_db
class TestCoordinatorDeleteSubject:
    """TC-C05 — Delete a catalog subject."""

    def test_delete_subject_removes_it_and_its_catalog_course(
        self, client, coordinator, managed_subject
    ):
        client.force_login(coordinator)

        response = client.post(
            reverse("coordinator:subject_delete", args=[managed_subject.pk])
        )

        assert response.status_code == 302
        assert not Subject.objects.filter(pk=managed_subject.pk).exists()
        assert not Course.objects.filter(code="COORD101").exists()

    def test_cannot_delete_a_subject_of_another_department(
        self, client, coordinator, subject
    ):
        """Actual error: subject outside the managed programs."""
        client.force_login(coordinator)

        response = client.post(reverse("coordinator:subject_delete", args=[subject.pk]))

        assert response.status_code == 404
        assert Subject.objects.filter(pk=subject.pk).exists()

    def test_delete_requires_a_post_request(self, client, coordinator, managed_subject):
        """Actual error: GET on a destructive endpoint."""
        client.force_login(coordinator)

        response = client.get(
            reverse("coordinator:subject_delete", args=[managed_subject.pk])
        )

        assert response.status_code == 405
        assert Subject.objects.filter(pk=managed_subject.pk).exists()


@pytest.mark.django_db
class TestCoordinatorUserAccounts:
    """TC-C06 — Approve, deactivate, archive and restore accounts."""

    @pytest.fixture
    def pending_faculty(self, coordinator):
        return User.objects.create_user(
            email="pending.faculty@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=coordinator.department,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )

    def test_user_list_shows_only_own_department_faculty(
        self, client, coordinator, professor, other_department
    ):
        outsider = User.objects.create_user(
            email="outsider@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=other_department,
        )
        client.force_login(coordinator)

        response = client.get(reverse("campus:user_list"))

        assert response.status_code == 200
        listed = [user.pk for user in response.context["users"]]
        assert professor.pk in listed
        assert outsider.pk not in listed

    def test_approve_pending_faculty(self, client, coordinator, pending_faculty):
        client.force_login(coordinator)

        response = client.post(
            reverse("campus:approve_user", args=[pending_faculty.pk])
        )

        assert response.status_code == 302
        pending_faculty.refresh_from_db()
        assert pending_faculty.approval_status == User.ApprovalStatus.APPROVED
        assert pending_faculty.is_active is True

    def test_cannot_approve_faculty_from_another_department(
        self, client, coordinator, other_department
    ):
        """Actual error: user outside the coordinator's scope."""
        outsider = User.objects.create_user(
            email="outsider.pending@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=other_department,
            approval_status=User.ApprovalStatus.PENDING,
            is_active=False,
        )
        client.force_login(coordinator)

        response = client.post(reverse("campus:approve_user", args=[outsider.pk]))

        assert response.status_code == 404
        outsider.refresh_from_db()
        assert outsider.approval_status == User.ApprovalStatus.PENDING

    def test_cannot_manage_the_own_account(self, client, coordinator):
        """Actual error: the coordinator account is outside the managed scope."""
        client.force_login(coordinator)

        response = client.post(
            reverse("campus:toggle_active", args=[coordinator.pk]),
        )

        assert response.status_code == 404
        coordinator.refresh_from_db()
        assert coordinator.is_active is True

    def test_archive_and_restore_a_student(self, client, coordinator, managed_student):
        client.force_login(coordinator)

        response = client.post(
            reverse("campus:archive_user", args=[managed_student.pk])
        )
        assert response.status_code == 302
        managed_student.refresh_from_db()
        assert managed_student.is_archived is True
        assert managed_student.is_active is False

        response = client.post(
            reverse("campus:restore_user", args=[managed_student.pk])
        )
        assert response.status_code == 302
        managed_student.refresh_from_db()
        assert managed_student.is_archived is False
        assert managed_student.is_active is True


@pytest.mark.django_db
class TestCoordinatorSectionsAndAssignments:
    """TC-C07 — Program sections and teaching assignments."""

    def test_section_list_shows_only_managed_program_sections(
        self, client, coordinator, managed_section, program_section
    ):
        client.force_login(coordinator)

        response = client.get(reverse("campus:section_list"))

        assert response.status_code == 200
        listed = [section.pk for section in response.context["sections"]]
        assert managed_section.pk in listed
        assert program_section.pk not in listed

    def test_create_section_for_a_managed_program(
        self, client, coordinator, managed_program, year_level, academic_year
    ):
        client.force_login(coordinator)

        response = client.post(
            reverse("campus:section_create"),
            {
                "program": managed_program.pk,
                "year_level": year_level.pk,
                "label": "2",
                "academic_year": academic_year.pk,
                "max_students": 30,
            },
        )

        assert response.status_code == 302
        assert ProgramSection.objects.filter(
            program=managed_program, label="2", max_students=30
        ).exists()

    def test_create_section_rejects_a_non_numeric_label(
        self, client, coordinator, managed_program, year_level, academic_year
    ):
        """Actual error: section label must be a number."""
        client.force_login(coordinator)

        response = client.post(
            reverse("campus:section_create"),
            {
                "program": managed_program.pk,
                "year_level": year_level.pk,
                "label": "A",
                "academic_year": academic_year.pk,
                "max_students": 30,
            },
        )

        assert response.status_code == 200
        assert "Section label must be a number" in response.content.decode()
        assert not ProgramSection.objects.filter(
            program=managed_program, label="A"
        ).exists()

    def test_create_teaching_assignment(
        self,
        client,
        coordinator,
        professor,
        managed_section,
        managed_subject,
        academic_term,
    ):
        client.force_login(coordinator)

        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": professor.pk,
                "program_sections": [managed_section.pk],
                "subject": managed_subject.pk,
                "term": academic_term.pk,
            },
        )

        assert response.status_code == 302
        assert TeachingAssignment.objects.filter(
            professor=professor,
            program_section=managed_section,
            subject=managed_subject,
        ).exists()

    def test_create_teaching_assignment_requires_a_section(
        self, client, coordinator, professor, managed_subject, academic_term
    ):
        """Actual error: no section selected."""
        client.force_login(coordinator)

        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": professor.pk,
                "program_sections": [],
                "subject": managed_subject.pk,
                "term": academic_term.pk,
            },
        )

        assert response.status_code == 302
        assert not TeachingAssignment.objects.exists()

    def test_cannot_open_the_chairperson_analytics_console(self, client, coordinator):
        """Actual error: role mismatch."""
        client.force_login(coordinator)

        response = client.get(reverse("analytics_chairperson:dashboard"))

        assert response.status_code == 403

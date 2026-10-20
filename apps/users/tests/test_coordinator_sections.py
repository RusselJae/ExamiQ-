"""Coordinator section management filters, pagination, and scoping tests."""

import pytest
from django.urls import reverse

from apps.questions.models import YearLevel
from apps.users.models import Department, Program, ProgramSection, User


@pytest.fixture
def coordinator(department):
    return User.objects.create_user(
        email="sections-coordinator@test.edu",
        password="testpass123",
        role=User.Role.PROGRAM_COORDINATOR,
        department=department,
    )


@pytest.fixture
def managed_program(department):
    return Program.objects.create(
        slug="sections-managed-program",
        name="Sections Managed Program",
        managing_department=department,
    )


def _create_section(program, year_level, academic_year, label):
    return ProgramSection.objects.create(
        program=program,
        year_level=year_level,
        academic_year=academic_year,
        label=label,
        max_students=40,
    )


@pytest.mark.django_db
class TestCoordinatorSectionList:
    def test_list_exposes_filters_columns_and_pagination(
        self, client, coordinator, managed_program, year_level, academic_year
    ):
        for index in range(1, 27):
            _create_section(
                managed_program,
                year_level,
                academic_year,
                f"S{index:02d}",
            )
        client.force_login(coordinator)

        response = client.get(reverse("campus:section_list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert managed_program.name in content
        assert year_level.name in content
        assert academic_year.label in content
        assert "All year levels" in content
        assert "Academic year" in content
        assert "min-w-[52rem]" in content
        assert "Page 1 of 2" in content
        assert "Academic Calendar" in content

    def test_filters_by_program_and_year_level(
        self,
        client,
        coordinator,
        department,
        managed_program,
        year_level,
        academic_year,
    ):
        first_year, _ = YearLevel.objects.get_or_create(
            order=1, defaults={"name": "1st Year"}
        )
        second_program = Program.objects.create(
            slug="sections-second-program",
            name="Sections Second Program",
            managing_department=department,
        )
        target = _create_section(
            managed_program,
            first_year,
            academic_year,
            "AA",
        )
        other_program_section = _create_section(
            second_program,
            first_year,
            academic_year,
            "BB",
        )
        other_year_section = _create_section(
            managed_program,
            year_level,
            academic_year,
            "CC",
        )
        client.force_login(coordinator)

        response = client.get(
            reverse("campus:section_list"),
            {"program": managed_program.pk, "year_level": first_year.pk},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert target.display_label in content
        assert other_program_section.display_label not in content
        assert other_year_section.display_label not in content

    def test_only_sections_from_managed_programs_are_listed(
        self, client, coordinator, year_level, academic_year
    ):
        other_department = Department.objects.create(name="Other Section Department")
        other_program = Program.objects.create(
            slug="sections-other-program",
            name="Other Sections Program",
            managing_department=other_department,
        )
        other_section = _create_section(
            other_program,
            year_level,
            academic_year,
            "ZZ",
        )
        client.force_login(coordinator)

        response = client.get(reverse("campus:section_list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert other_section.display_label not in content
        assert other_program.name not in content

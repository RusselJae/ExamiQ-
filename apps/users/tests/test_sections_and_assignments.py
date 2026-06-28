import pytest
from django.core import mail
from django.urls import reverse

from apps.questions.models import YearLevel
from apps.users.models import AcademicTerm, AcademicYear, ProgramSection, User


@pytest.mark.django_db
class TestCampusSections:
    def test_campus_admin_can_list_sections(self, client, program_section):
        admin = User.objects.create_superuser(
            email="admin@test.edu",
            password="testpass123",
        )
        client.force_login(admin)
        response = client.get(reverse("campus:section_list"))
        assert response.status_code == 200
        assert program_section.display_label in response.content.decode()

    def test_bulk_create_sections(self, client, program, year_level, academic_year):
        admin = User.objects.create_superuser(
            email="admin@test.edu",
            password="testpass123",
        )
        client.force_login(admin)
        response = client.post(
            reverse("campus:section_bulk"),
            {
                "program": program.pk,
                "year_level": year_level.pk,
                "academic_year": academic_year.pk,
                "section_count": 3,
                "max_students": 30,
            },
        )
        assert response.status_code == 302
        assert ProgramSection.objects.filter(program=program, year_level=year_level).count() >= 3


    def test_bulk_create_sections_uses_numeric_labels(
        self, client, program, year_level, academic_year
    ):
        admin = User.objects.create_superuser(
            email="admin@test.edu",
            password="testpass123",
        )
        client.force_login(admin)
        response = client.post(
            reverse("campus:section_bulk"),
            {
                "program": program.pk,
                "year_level": year_level.pk,
                "academic_year": academic_year.pk,
                "section_count": 3,
                "max_students": 30,
            },
        )
        assert response.status_code == 302
        labels = set(
            ProgramSection.objects.filter(program=program, year_level=year_level).values_list(
                "label", flat=True
            )
        )
        assert {"1", "2", "3"}.issubset(labels)


@pytest.mark.django_db
class TestAssignmentSubjectsAPI:
    def test_api_filters_by_section_year_and_term_semester(
        self, client, chairperson, program_section, subject, program, year_level
    ):
        from apps.questions.models import Subject as SubjectModel

        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        other_year, _ = YearLevel.objects.get_or_create(
            order=99, defaults={"name": "4th Year"}
        )
        fourth_year_section = ProgramSection.objects.create(
            program=program,
            year_level=other_year,
            label="1",
            academic_year=program_section.academic_year,
        )
        SubjectModel.objects.create(
            program=program,
            code="COSC-50",
            name="Advanced Course",
            year_level=other_year,
            semester=1,
        )
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            semester=AcademicTerm.Semester.FIRST,
            is_current=True,
        )
        client.force_login(chairperson)
        response = client.get(
            reverse("analytics_chairperson:assignment_subjects_api"),
            {"section": fourth_year_section.pk, "term": term.pk},
        )
        assert response.status_code == 200
        codes = {s["code"] for s in response.json()["subjects"]}
        assert "COSC-50" in codes
        assert subject.code not in codes or subject.year_level_id == other_year.id


@pytest.mark.django_db
class TestApprovalNotifications:
    def test_approve_sends_email_and_notification(self, client, department):
        admin = User.objects.create_superuser(
            email="admin@test.edu",
            password="testpass123",
        )
        pending = User.objects.create_user(
            email="pending@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        mail.outbox.clear()
        client.force_login(admin)
        response = client.post(reverse("campus:approve_user", kwargs={"pk": pending.pk}))
        assert response.status_code == 302
        pending.refresh_from_db()
        assert pending.is_active is True
        assert len(mail.outbox) == 1
        assert pending.notifications.filter(message__icontains="approved").exists()

    def test_reject_sends_email_and_notification(self, client, department):
        admin = User.objects.create_superuser(
            email="admin@test.edu",
            password="testpass123",
        )
        pending = User.objects.create_user(
            email="reject@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=department,
            phone_number="09123456789",
            is_active=False,
            approval_status=User.ApprovalStatus.PENDING,
        )
        mail.outbox.clear()
        client.force_login(admin)
        response = client.post(reverse("campus:reject_user", kwargs={"pk": pending.pk}))
        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert pending.notifications.filter(message__icontains="not approved").exists()


@pytest.mark.django_db
class TestSectionsAPI:
    def test_sections_api_returns_active_sections(self, client, program_section):
        response = client.get(
            reverse("users:api_sections"),
            {"program": "cs", "year_level": program_section.year_level_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sections"]) == 1
        assert data["sections"][0]["id"] == program_section.pk


@pytest.mark.django_db
class TestTeachingAssignments:
    def test_chairperson_can_create_assignment(
        self, client, chairperson, professor, program_section, subject, program
    ):
        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            is_current=True,
        )
        client.force_login(chairperson)
        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": professor.pk,
                "program_section": program_section.pk,
                "subject": subject.pk,
                "term": term.pk,
            },
        )
        assert response.status_code == 302
        assert professor.teaching_assignments.count() == 1

    def test_professor_with_assignments_cannot_self_create_course(self, client, professor, program_section, subject):
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
        )
        from apps.users.assignment_services import create_teaching_assignment

        create_teaching_assignment(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=term,
            assigned_by=User.objects.filter(role=User.Role.CHAIRPERSON).first()
            or User.objects.create_user(
                email="chair2@test.edu",
                password="x",
                role=User.Role.CHAIRPERSON,
                department=program_section.program.managing_department,
            ),
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_create"))
        assert response.status_code == 302

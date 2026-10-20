import pytest
from django.core import mail
from django.urls import reverse

from apps.questions.models import Subject, YearLevel
from apps.users.models import AcademicTerm, ProgramSection, User


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
        assert program_section.display_label == "BSCS 2-1M"
        assert "Computer Science ·" not in response.content.decode()

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
    def test_api_lists_all_year_subjects_regardless_of_semester(
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
        SubjectModel.objects.create(
            program=program,
            code="COSC-51",
            name="Second Semester Course",
            year_level=other_year,
            semester=2,
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
        assert "COSC-51" in codes
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
        professor.department = program.managing_department
        professor.save(update_fields=["department"])
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
                "program_sections": [program_section.pk],
                "subject": subject.pk,
                "term": term.pk,
            },
        )
        assert response.status_code == 302
        assert professor.teaching_assignments.count() == 1

    def test_sections_api_filters_by_subject_year_level(
        self, client, chairperson, professor, program_section, subject, program, year_level
    ):
        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        other_year, _ = YearLevel.objects.get_or_create(
            order=99, defaults={"name": "4th Year"}
        )
        wrong_year_section = ProgramSection.objects.create(
            program=program,
            year_level=other_year,
            label="4X",
            academic_year=program_section.academic_year,
            is_active=True,
        )
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            is_current=True,
        )
        client.force_login(chairperson)
        response = client.get(
            reverse("analytics_chairperson:assignment_sections_api"),
            {"subject": subject.pk, "term": term.pk},
        )
        assert response.status_code == 200
        section_ids = {
            s["id"]
            for group in response.json()["groups"]
            for s in group["sections"]
        }
        assert program_section.pk in section_ids
        assert wrong_year_section.pk not in section_ids

    def test_year_mismatch_surfaces_real_error(
        self, client, chairperson, professor, program_section, subject, program
    ):
        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        professor.department = program.managing_department
        professor.save(update_fields=["department"])
        other_year, _ = YearLevel.objects.get_or_create(
            order=98, defaults={"name": "3rd Year"}
        )
        wrong_section = ProgramSection.objects.create(
            program=program,
            year_level=other_year,
            label="3Z",
            academic_year=program_section.academic_year,
            is_active=True,
        )
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            is_current=True,
        )
        client.force_login(chairperson)
        # Matching-year section first keeps the subject in the form queryset;
        # the wrong-year section then fails validate_assignment_subject.
        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": professor.pk,
                "program_sections": [program_section.pk, wrong_section.pk],
                "subject": subject.pk,
                "term": term.pk,
            },
            follow=True,
        )
        assert response.status_code == 200
        assert professor.teaching_assignments.count() == 0
        content = response.content.decode()
        assert "year level" in content.lower()
        assert "Could not create assignment. Check the form." not in content

    def test_chairperson_can_assign_multiple_sections(
        self, client, chairperson, professor, program_section, subject, program, year_level
    ):
        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        professor.department = program.managing_department
        professor.save(update_fields=["department"])
        second_section = ProgramSection.objects.create(
            program=program,
            year_level=year_level,
            label="2-B",
            academic_year=program_section.academic_year,
            is_active=True,
        )
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
                "program_sections": [program_section.pk, second_section.pk],
                "subject": subject.pk,
                "term": term.pk,
            },
        )
        assert response.status_code == 302
        assert professor.teaching_assignments.count() == 2
        from apps.reviews.models import ExamSetup

        assert ExamSetup.objects.filter(course__professor=professor).count() == 2

    def test_chairperson_can_assign_cross_semester_subject(
        self, client, chairperson, professor, program_section, program, year_level
    ):
        from apps.questions.models import Subject as SubjectModel

        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        professor.department = program.managing_department
        professor.save(update_fields=["department"])
        cross_subject = SubjectModel.objects.create(
            program=program,
            code="COSC-60",
            name="Second Semester Course",
            year_level=year_level,
            semester=2,
        )
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            semester=AcademicTerm.Semester.FIRST,
            is_current=True,
        )
        client.force_login(chairperson)
        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": professor.pk,
                "program_sections": [program_section.pk],
                "subject": cross_subject.pk,
                "term": term.pk,
            },
        )
        assert response.status_code == 302
        assert professor.teaching_assignments.filter(subject=cross_subject).count() == 1

    def test_professor_cannot_self_create_catalog_course(
        self, client, professor, program_section, subject, year_level, bsed_program
    ):
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_create"))
        assert response.status_code == 403

        response = client.post(
            reverse("analytics_professor:course_create"),
            {
                "code": "BSEM 99",
                "name": "New Catalog Course",
                "year_level": year_level.pk,
                "semester": 1,
            },
        )
        assert response.status_code == 403
        assert not Subject.objects.filter(
            program=bsed_program, code="BSEM 99"
        ).exists()

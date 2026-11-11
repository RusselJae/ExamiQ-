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

    def test_section_list_shows_teaching_faculty(
        self, client, professor, teaching_assignment
    ):
        """Faculty column names the professors teaching each section."""
        from apps.users.models import TeachingAssignment

        admin = User.objects.create_superuser(
            email="admin2@test.edu",
            password="testpass123",
        )
        client.force_login(admin)
        assignment = TeachingAssignment.objects.select_related(
            "professor", "program_section"
        ).first()
        assert assignment is not None
        content = client.get(reverse("campus:section_list")).content.decode()
        assert "Faculty" in content
        name = assignment.professor.get_full_name() or assignment.professor.email
        assert name in content

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
        assert (
            ProgramSection.objects.filter(
                program=program, year_level=year_level
            ).count()
            >= 3
        )

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
            ProgramSection.objects.filter(
                program=program, year_level=year_level
            ).values_list("label", flat=True)
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
        response = client.post(
            reverse("campus:approve_user", kwargs={"pk": pending.pk})
        )
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

    def test_chairperson_must_pick_at_least_one_section(
        self, client, chairperson, professor, program_section, subject, program
    ):
        """Sections are required: a faculty member handles named cohorts."""
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
                "subject": subject.pk,
                "term": term.pk,
            },
        )
        assert response.status_code == 302
        from django.contrib.messages import get_messages

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("Select at least one section." in text for text in texts)
        assert not professor.teaching_assignments.filter(subject=subject).exists()

    def test_sections_api_filters_by_subject_year_level(
        self,
        client,
        chairperson,
        professor,
        program_section,
        subject,
        program,
        year_level,
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
            s["id"] for group in response.json()["groups"] for s in group["sections"]
        }
        assert program_section.pk in section_ids
        assert wrong_year_section.pk not in section_ids

    def test_year_mismatch_sections_are_ignored(
        self, client, chairperson, professor, program_section, subject, program
    ):
        """A section from another year level is rejected, not silently used."""
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
        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": professor.pk,
                "program_sections": [program_section.pk, wrong_section.pk],
                "subject": subject.pk,
                "term": term.pk,
            },
        )
        assert response.status_code == 302
        from django.contrib.messages import get_messages

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("Subject year level must match" in text for text in texts)
        assert not professor.teaching_assignments.filter(subject=subject).exists()

    def test_chairperson_assigns_course_per_selected_section(
        self,
        client,
        chairperson,
        professor,
        program_section,
        subject,
        program,
        year_level,
    ):
        """Two selected sections create two rows (the two-section cap)."""
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
        assert professor.teaching_assignments.filter(subject=subject).count() == 2
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
        assert not Subject.objects.filter(program=bsed_program, code="BSEM 99").exists()


@pytest.mark.django_db
class TestHandledVisibilityScope:
    def test_visible_students_follow_assignments(
        self, professor, student, subject, academic_year, bsed_program
    ):
        from apps.users.assignment_services import students_visible_to_faculty
        from apps.users.models import StudentFacultyAssignment

        subject.program = bsed_program
        subject.save(update_fields=["program_id"])
        assert students_visible_to_faculty(professor) == set()
        StudentFacultyAssignment.objects.create(
            student=student,
            faculty=professor,
            subject=subject,
            academic_year=academic_year,
        )
        assert students_visible_to_faculty(professor) == {student.pk}

    def test_students_with_completed_exams_stay_visible_without_assignment(
        self,
        professor,
        student,
        subject,
        topic,
        academic_year,
        bsed_program,
        academic_term,
        program_section,
    ):
        """Section-enrolled students who sat exams stay visible (no SFA row).

        Regression: before sections were removed from the flow, visibility
        followed section enrollment + completed exams on handled subjects.
        Students who answered exams then vanished, even though the faculty
        still handles the course.
        """
        from apps.reviews.models import ReviewSession
        from apps.users.assignment_services import (
            create_teaching_assignment,
            handled_subject_ids,
            students_visible_to_faculty,
        )
        from apps.users.models import ProgramSection

        subject.program = bsed_program
        subject.save(update_fields=["program_id"])
        topic.subject = subject
        topic.save(update_fields=["subject"])
        section, _ = ProgramSection.objects.get_or_create(
            program=subject.program,
            year_level=subject.year_level,
            label="1M",
            academic_year=academic_year,
            defaults={"max_students": 40},
        )
        student.section = section
        student.save(update_fields=["section"])
        create_teaching_assignment(
            professor=professor,
            program_section=section,
            subject=subject,
            term=academic_term,
            assigned_by=professor,
        )
        assert subject.pk in handled_subject_ids(professor)

        ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty="easy",
            status=ReviewSession.Status.COMPLETED,
        )
        assert students_visible_to_faculty(professor) == {student.pk}

    def test_session_without_section_or_assignment_stays_hidden(
        self, professor, subject, topic, academic_term, program_section
    ):
        """A completed exam alone is not enough without section enrollment."""
        from apps.reviews.models import ReviewSession
        from apps.users.assignment_services import (
            create_teaching_assignment,
            students_visible_to_faculty,
        )
        from apps.users.models import User

        create_teaching_assignment(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=academic_term,
            assigned_by=professor,
        )
        outsider = User.objects.create_user(
            email="sectionless@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
        )
        ReviewSession.objects.create(
            student=outsider,
            topic=topic,
            difficulty="easy",
            status=ReviewSession.Status.COMPLETED,
        )
        visible = students_visible_to_faculty(professor)
        assert outsider.pk not in visible

    def test_handled_subject_ids_prefer_teaching_assignments(
        self, professor, teaching_assignment, subject
    ):
        from apps.users.assignment_services import handled_subject_ids

        assert handled_subject_ids(professor) == {subject.pk}

    def test_handled_subject_ids_fall_back_to_profile(self, professor, subject):
        from apps.users.assignment_services import handled_subject_ids

        professor.assigned_subjects.add(subject)
        assert handled_subject_ids(professor) == {subject.pk}

    def test_course_list_splits_handled_and_other(
        self,
        client,
        professor,
        program_section,
        bsed_program,
        year_level,
        academic_term,
    ):
        from apps.questions.models import Subject as SubjectModel
        from apps.users.models import TeachingAssignment

        handled = SubjectModel.objects.create(
            program=bsed_program,
            code="TEST-201",
            name="Handled Subject",
            year_level=year_level,
            semester=1,
        )
        SubjectModel.objects.create(
            program=bsed_program,
            code="TEST-202",
            name="Other Subject",
            year_level=year_level,
            semester=1,
        )
        TeachingAssignment.objects.create(
            professor=professor,
            program_section=program_section,
            subject=handled,
            term=academic_term,
            assigned_by=professor,
        )
        client.force_login(professor)
        response = client.get(reverse("analytics_professor:course_list"))
        assert response.status_code == 200
        handled_cards = response.context["handled_course_cards"]
        other_cards = response.context["other_course_cards"]
        assert {c["subject"].code for c in handled_cards} == {"TEST-201"}
        assert "TEST-202" in {c["subject"].code for c in other_cards}
        assert "TEST-201" not in {c["subject"].code for c in other_cards}
        content = response.content.decode()
        assert "Subjects you handle" in content
        # Unhandled subjects are hidden from the faculty grid (still reachable
        # by direct URL); only handled courses render as cards.
        assert "Other subjects" not in content
        assert "TEST-202" not in content


@pytest.mark.django_db
class TestTeachingAssignmentReassign:
    def _dept(self, chairperson, professor, program):
        chairperson.department = program.managing_department
        chairperson.save(update_fields=["department"])
        professor.department = program.managing_department
        professor.save(update_fields=["department"])

    def _term(self, program_section):
        return AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            is_current=True,
        )

    def _other_professor(self, program):
        from apps.users.models import User

        return User.objects.create_user(
            email="other.prof@test.edu",
            password="testpass123",
            role=User.Role.PROFESSOR,
            department=program.managing_department,
        )

    def test_chairperson_can_reassign_to_another_professor(
        self, client, chairperson, professor, program_section, subject, program
    ):
        from apps.users.models import TeachingAssignment

        self._dept(chairperson, professor, program)
        other = self._other_professor(program)
        term = self._term(program_section)
        assignment = TeachingAssignment.objects.create(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=term,
            assigned_by=chairperson,
        )
        client.force_login(chairperson)
        list_resp = client.get(reverse("analytics_chairperson:assignments"))
        assert list_resp.status_code == 200
        assert "Reassign" in list_resp.content.decode()
        response = client.get(
            reverse(
                "analytics_chairperson:assignment_reassign",
                kwargs={"pk": assignment.pk},
            )
        )
        assert response.status_code == 200
        response = client.post(
            reverse(
                "analytics_chairperson:assignment_reassign",
                kwargs={"pk": assignment.pk},
            ),
            {"professor": other.pk},
        )
        assert response.status_code == 302
        assignment.refresh_from_db()
        assert assignment.professor_id == other.pk

    def test_reassign_conflict_is_rejected(
        self, client, chairperson, professor, program_section, subject, program
    ):
        """Reassigning onto a course the target already handles is rejected,
        no matter which section row it came from."""
        from apps.users.models import TeachingAssignment

        self._dept(chairperson, professor, program)
        other = self._other_professor(program)
        term = self._term(program_section)
        mine = TeachingAssignment.objects.create(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=term,
            assigned_by=chairperson,
        )
        TeachingAssignment.objects.create(
            professor=other,
            program_section=program_section,
            subject=subject,
            term=term,
            assigned_by=chairperson,
        )
        client.force_login(chairperson)
        response = client.post(
            reverse(
                "analytics_chairperson:assignment_reassign", kwargs={"pk": mine.pk}
            ),
            {"professor": other.pk},
        )
        assert response.status_code == 302
        mine.refresh_from_db()
        assert mine.professor_id == professor.pk

    def test_reassign_outside_department_is_blocked(
        self, client, chairperson, professor, program_section, subject, program
    ):
        from apps.users.models import Department, TeachingAssignment

        other_dept, _ = Department.objects.get_or_create(name="Other College")
        chairperson.department = other_dept
        chairperson.save(update_fields=["department"])
        term = self._term(program_section)
        assignment = TeachingAssignment.objects.create(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=term,
            assigned_by=chairperson,
        )
        client.force_login(chairperson)
        response = client.get(
            reverse(
                "analytics_chairperson:assignment_reassign",
                kwargs={"pk": assignment.pk},
            )
        )
        assert response.status_code == 302


@pytest.mark.django_db
class TestTeachingAssignmentUniqueness:
    """One row per faculty + course + term + section, enforced in the DB."""

    def _other_section(self, program_section):
        from apps.users.models import ProgramSection

        return ProgramSection.objects.create(
            program=program_section.program,
            year_level=program_section.year_level,
            label="9Z",
            academic_year=program_section.academic_year,
            is_active=True,
        )

    def test_duplicate_row_for_same_section_is_rejected(
        self, professor, program_section, subject, academic_term
    ):
        from django.db import IntegrityError, transaction

        from apps.users.models import TeachingAssignment

        TeachingAssignment.objects.create(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=academic_term,
            assigned_by=professor,
        )
        with transaction.atomic(), pytest.raises(IntegrityError):
            TeachingAssignment.objects.create(
                professor=professor,
                program_section=program_section,
                subject=subject,
                term=academic_term,
                assigned_by=professor,
            )

    def test_different_sections_create_separate_rows(
        self, professor, program_section, subject, academic_term
    ):
        from apps.users.models import TeachingAssignment

        TeachingAssignment.objects.create(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=academic_term,
            assigned_by=professor,
        )
        TeachingAssignment.objects.create(
            professor=professor,
            program_section=self._other_section(program_section),
            subject=subject,
            term=academic_term,
            assigned_by=professor,
        )
        assert (
            TeachingAssignment.objects.filter(
                professor=professor, subject=subject, term=academic_term
            ).count()
            == 2
        )

    def test_create_service_returns_existing_row_for_same_section(
        self, professor, program_section, subject, academic_term, chairperson
    ):
        from apps.users.assignment_services import create_teaching_assignment
        from apps.users.models import TeachingAssignment

        first, created_first = create_teaching_assignment(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=academic_term,
            assigned_by=chairperson,
        )
        second, created_second = create_teaching_assignment(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=academic_term,
            assigned_by=chairperson,
        )
        assert created_first is True
        assert created_second is False
        assert first.pk == second.pk
        assert (
            TeachingAssignment.objects.filter(
                professor=professor, subject=subject, term=academic_term
            ).count()
            == 1
        )

    def test_create_service_blocks_a_third_section(
        self, professor, program_section, subject, academic_term, chairperson
    ):
        from apps.users.assignment_services import create_teaching_assignment
        from apps.users.models import ProgramSection, TeachingAssignment

        create_teaching_assignment(
            professor=professor,
            program_section=program_section,
            subject=subject,
            term=academic_term,
            assigned_by=chairperson,
        )
        create_teaching_assignment(
            professor=professor,
            program_section=self._other_section(program_section),
            subject=subject,
            term=academic_term,
            assigned_by=chairperson,
        )
        other = ProgramSection.objects.create(
            program=program_section.program,
            year_level=program_section.year_level,
            label="8Y",
            academic_year=program_section.academic_year,
            is_active=True,
        )
        with pytest.raises(ValueError, match="at most 2 sections"):
            create_teaching_assignment(
                professor=professor,
                program_section=other,
                subject=subject,
                term=academic_term,
                assigned_by=chairperson,
            )
        assert (
            TeachingAssignment.objects.filter(
                professor=professor, subject=subject, term=academic_term
            ).count()
            == 2
        )


@pytest.mark.django_db
class TestTwoFacultyPerSubjectTerm:
    """At most two faculty may handle the same subject in one term."""

    def _other_professor(self, email="second.prof@test.edu"):
        from apps.users.models import User

        return User.objects.create_user(
            email=email,
            password="testpass123",
            role=User.Role.PROFESSOR,
        )

    def _other_section(self, program_section, label="9Z"):
        from apps.users.models import ProgramSection

        return ProgramSection.objects.create(
            program=program_section.program,
            year_level=program_section.year_level,
            label=label,
            academic_year=program_section.academic_year,
            is_active=True,
        )

    def test_third_faculty_assignment_is_rejected_with_message(
        self, professor, program_section, subject, academic_term, chairperson
    ):
        from apps.users.assignment_services import create_teaching_assignments

        second = self._other_professor()
        third = self._other_professor("third.prof@test.edu")
        sections = [
            program_section,
            self._other_section(program_section, label="9Z"),
            self._other_section(program_section, label="8Y"),
        ]
        for prof, section in zip((professor, second), sections):
            result = create_teaching_assignments(
                professor=prof,
                program_sections=[section],
                subject=subject,
                term=academic_term,
                assigned_by=chairperson,
            )
            assert result["created"] == 1

        with pytest.raises(ValueError, match="at most 2|Only up to 2"):
            create_teaching_assignments(
                professor=third,
                program_sections=[sections[2]],
                subject=subject,
                term=academic_term,
                assigned_by=chairperson,
            )

    def test_reassign_into_full_subject_is_rejected(
        self, professor, program_section, subject, academic_term, chairperson
    ):
        from apps.users.assignment_services import reassign_teaching_assignment
        from apps.users.models import TeachingAssignment

        second = self._other_professor()
        for prof, section in (
            (professor, program_section),
            (second, self._other_section(program_section, label="9Z")),
        ):
            TeachingAssignment.objects.create(
                professor=prof,
                program_section=section,
                subject=subject,
                term=academic_term,
                assigned_by=chairperson,
            )
        # Legacy third row created directly (the service would have blocked it).
        roving = TeachingAssignment.objects.create(
            professor=self._other_professor("roving.prof@test.edu"),
            program_section=self._other_section(program_section, label="8Y"),
            subject=subject,
            term=academic_term,
            assigned_by=chairperson,
        )
        with pytest.raises(ValueError, match="at most 2|Only up to 2"):
            reassign_teaching_assignment(
                roving,
                professor=self._other_professor("third.prof@test.edu"),
            )
        assert (
            TeachingAssignment.objects.filter(
                subject=subject, term=academic_term
            ).count()
            == 3
        )

    def test_assign_view_shows_friendly_error_instead_of_500(
        self, client, chairperson, professor, program_section, subject, program
    ):
        from apps.users.models import AcademicTerm, TeachingAssignment

        dept = program.managing_department
        chairperson.department = dept
        chairperson.save(update_fields=["department"])
        professor.department = dept
        professor.save(update_fields=["department"])
        second = self._other_professor()
        second.department = dept
        second.save(update_fields=["department"])
        term = AcademicTerm.objects.create(
            academic_year=program_section.academic_year,
            name="1st Sem",
            is_current=True,
        )
        for prof, section in (
            (professor, program_section),
            (second, self._other_section(program_section, label="9Z")),
        ):
            TeachingAssignment.objects.create(
                professor=prof,
                program_section=section,
                subject=subject,
                term=term,
                assigned_by=chairperson,
            )
        third = self._other_professor("third.prof@test.edu")
        third.department = dept
        third.save(update_fields=["department"])
        client.force_login(chairperson)
        response = client.post(
            reverse("analytics_chairperson:assignment_create"),
            {
                "professor": third.pk,
                "subject": subject.pk,
                "term": term.pk,
                "program_sections": [program_section.pk],
            },
        )
        assert response.status_code == 302
        from django.contrib.messages import get_messages

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("Only up to 2 faculty members" in text for text in texts)
        assert (
            TeachingAssignment.objects.filter(subject=subject, term=term)
            .values("professor_id")
            .distinct()
            .count()
            == 2
        )


@pytest.mark.django_db
class TestBackfillTeachingAssignments:
    def test_backfill_creates_assignments_from_profile(
        self, professor, program_section, subject, academic_year, academic_term
    ):
        from django.core.management import call_command

        from apps.users.models import TeachingAssignment

        professor.assigned_subjects.add(subject)
        professor.assigned_sections.add(program_section)

        call_command("backfill_teaching_assignments")

        assert (
            TeachingAssignment.objects.filter(
                professor=professor, subject=subject
            ).count()
            == 1
        )

        # Idempotent: a second run creates nothing new.
        call_command("backfill_teaching_assignments")
        assert TeachingAssignment.objects.filter(professor=professor).count() == 1

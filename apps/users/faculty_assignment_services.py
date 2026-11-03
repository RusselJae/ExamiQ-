"""Faculty assignment services for automatic student-faculty matching."""

from django.db import transaction

from apps.questions.models import Subject
from apps.users.models import (
    AcademicYear,
    StudentFacultyAssignment,
    TeachingAssignment,
    User,
)


def assign_faculty_to_student(student: User) -> None:
    """Automatically assign faculty to a student based on their subjects and TeachingAssignment.

    For regular students: assigns faculty based on year_level and program through TeachingAssignment.
    For irregular students: assigns faculty per selected course based on IrregularSubjectEnrollment.
    """
    if student.role != User.Role.STUDENT:
        return

    current_year = AcademicYear.get_current()
    if not current_year:
        return

    # Get subjects the student is taking
    subjects = get_student_subjects(student)
    if not subjects:
        return

    # Assign faculty for each subject
    with transaction.atomic():
        for subject in subjects:
            faculty = find_faculty_for_subject(student, subject, current_year)
            if faculty:
                StudentFacultyAssignment.objects.get_or_create(
                    student=student,
                    faculty=faculty,
                    subject=subject,
                    academic_year=current_year,
                )


def get_student_subjects(student: User) -> list[Subject]:
    """Get the subjects a student is enrolled in."""
    if student.is_irregular:
        # Irregular students have IrregularSubjectEnrollment records
        from apps.users.models import IrregularSubjectEnrollment

        enrollments = IrregularSubjectEnrollment.objects.filter(
            student=student, status=IrregularSubjectEnrollment.Status.ENROLLED
        ).select_related("subject")
        return [enrollment.subject for enrollment in enrollments]
    else:
        # Regular students have StudentSubject records
        from apps.users.models import StudentSubject

        student_subjects = StudentSubject.objects.filter(
            student=student
        ).select_related("subject")
        return [ss.subject for ss in student_subjects]


def find_faculty_for_subject(
    student: User, subject: Subject, academic_year: AcademicYear
) -> User | None:
    """Find the appropriate faculty member for a student-subject pair.

    Uses TeachingAssignment records to match faculty to subjects and sections.
    For regular students, matches by year_level and program.
    For irregular students, matches by the specific section they selected for that subject.
    """
    if student.is_irregular:
        # Irregular students: match by the section they selected for this subject
        from apps.users.models import IrregularSubjectEnrollment

        enrollment = IrregularSubjectEnrollment.objects.filter(
            student=student,
            subject=subject,
            status=IrregularSubjectEnrollment.Status.ENROLLED,
        ).first()

        if enrollment and enrollment.section:
            # Find TeachingAssignment for this subject and section
            assignment = (
                TeachingAssignment.objects.filter(
                    subject=subject,
                    program_section=enrollment.section,
                    term__academic_year=academic_year,
                )
                .select_related("professor")
                .first()
            )
            if assignment and assignment.professor:
                return assignment.professor
    else:
        # Regular students: match by year_level and program
        from apps.users.models import ProgramSection

        # Find sections for the student's year level and program
        program = student.home_program
        if not program or not student.year_level:
            return None

        sections = ProgramSection.objects.filter(
            program=program,
            year_level=student.year_level,
            academic_year=academic_year,
            is_active=True,
        )

        # Find TeachingAssignment for this subject in any of these sections
        for section in sections:
            assignment = (
                TeachingAssignment.objects.filter(
                    subject=subject,
                    program_section=section,
                    term__academic_year=academic_year,
                )
                .select_related("professor")
                .first()
            )
            if assignment and assignment.professor:
                return assignment.professor

    return None


def get_student_faculty_for_subject(student: User, subject: Subject) -> User | None:
    """Get the faculty member assigned to a student for a specific subject."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return None

    assignment = StudentFacultyAssignment.objects.filter(
        student=student, subject=subject, academic_year=current_year
    ).select_related("faculty")

    if assignment.exists():
        return assignment.first().faculty
    return None


def get_students_for_faculty(
    faculty: User, subject: Subject | None = None
) -> list[User]:
    """Get students assigned to a faculty member, optionally filtered by subject."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return []

    queryset = StudentFacultyAssignment.objects.filter(
        faculty=faculty, academic_year=current_year
    ).select_related("student")

    if subject:
        queryset = queryset.filter(subject=subject)

    student_ids = queryset.values_list("student_id", flat=True).distinct()
    return list(User.objects.filter(pk__in=student_ids, is_archived=False))


def get_faculty_for_student(student: User) -> list[User]:
    """Get all faculty members assigned to a student across all subjects."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return []

    faculty_ids = (
        StudentFacultyAssignment.objects.filter(
            student=student, academic_year=current_year
        )
        .values_list("faculty_id", flat=True)
        .distinct()
    )
    return list(User.objects.filter(pk__in=faculty_ids, role=User.Role.PROFESSOR))

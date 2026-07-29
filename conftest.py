import pytest
from django.contrib.auth import get_user_model

from apps.questions.models import Question, QuestionChoice, Subject, Topic, YearLevel
from apps.users.constants import PROGRAM_DEFINITIONS
from apps.users.models import AcademicTerm, AcademicYear, Course, Department, Program, ProgramSection

User = get_user_model()


@pytest.fixture
def department(db):
    dept, _ = Department.objects.get_or_create(name="Test Department")
    return dept


@pytest.fixture
def program(db, department):
    slug, name, dept_name = PROGRAM_DEFINITIONS[0]
    dept, _ = Department.objects.get_or_create(name=dept_name)
    prog, _ = Program.objects.get_or_create(
        slug=slug,
        defaults={"name": name, "managing_department": dept},
    )
    return prog


@pytest.fixture
def year_level(db):
    yl, _ = YearLevel.objects.get_or_create(order=2, defaults={"name": "2nd Year"})
    return yl


@pytest.fixture
def subject(db, program, year_level):
    subj, _ = Subject.objects.get_or_create(
        program=program,
        code="TEST-101",
        defaults={
            "year_level": year_level,
            "semester": 1,
            "name": "Test Subject",
        },
    )
    return subj


@pytest.fixture
def topic(db, subject):
    return Topic.objects.create(subject=subject, name="Algebra")


@pytest.fixture
def bsed_program(db):
    edu, _ = Department.objects.get_or_create(name="College of Education")
    prog, _ = Program.objects.get_or_create(
        slug=User.HomeDegreeProgram.BSED_MATH,
        defaults={"name": "BSEd Mathematics", "managing_department": edu},
    )
    return prog


def make_bsed_student(student, *, subject=None, course=None, bsed_program=None):
    """Point student (and optional subject/course) at BSEd Math for open-exam tests."""
    if bsed_program is None:
        edu, _ = Department.objects.get_or_create(name="College of Education")
        bsed_program, _ = Program.objects.get_or_create(
            slug=User.HomeDegreeProgram.BSED_MATH,
            defaults={"name": "BSEd Mathematics", "managing_department": edu},
        )
    student.home_degree_program = User.HomeDegreeProgram.BSED_MATH
    student.save(update_fields=["home_degree_program"])
    if subject is not None:
        subject.program = bsed_program
        subject.save(update_fields=["program_id"])
    if course is not None:
        course.program = bsed_program
        course.save(update_fields=["program_id"])
    return bsed_program


@pytest.fixture
def academic_year(db):
    year, _ = AcademicYear.objects.get_or_create(
        label="2025-2026",
        defaults={"is_current": True},
    )
    return year


@pytest.fixture
def program_section(db, program, year_level, academic_year):
    section, _ = ProgramSection.objects.get_or_create(
        program=program,
        year_level=year_level,
        label="1M",
        academic_year=academic_year,
        defaults={"max_students": 40},
    )
    return section


@pytest.fixture
def academic_term(db, academic_year):
    term, _ = AcademicTerm.objects.get_or_create(
        academic_year=academic_year,
        name="1st Sem",
        defaults={
            "is_current": True,
            "semester": AcademicTerm.Semester.FIRST,
        },
    )
    if not term.is_current:
        term.is_current = True
        term.save(update_fields=["is_current"])
    return term


@pytest.fixture
def teaching_assignment(db, professor, program_section, subject, academic_term, chairperson):
    from apps.users.assignment_services import create_teaching_assignment

    assignment, _ = create_teaching_assignment(
        professor=professor,
        program_section=program_section,
        subject=subject,
        term=academic_term,
        assigned_by=chairperson,
    )
    return assignment


@pytest.fixture
def student(db, department, year_level, program_section):
    return User.objects.create_user(
        email="student@test.edu",
        password="testpass123",
        role=User.Role.STUDENT,
        department=department,
        home_degree_program=User.HomeDegreeProgram.CS,
        year_level=year_level,
        section=program_section,
    )


@pytest.fixture
def professor(db, department):
    return User.objects.create_user(
        email="prof@test.edu",
        password="testpass123",
        role=User.Role.PROFESSOR,
        department=department,
    )


@pytest.fixture
def chairperson(db, department):
    return User.objects.create_user(
        email="chair@test.edu",
        password="testpass123",
        role=User.Role.CHAIRPERSON,
        department=department,
    )


@pytest.fixture
def course(db, professor, program):
    return Course.objects.create(
        program=program,
        code="T101",
        name="Test Course",
        professor=professor,
        term="1st Sem",
        academic_year="2026",
        section="A",
    )


@pytest.fixture
def mcq_question(db, topic):
    q = Question.objects.create(
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        question_type=Question.QuestionType.MCQ,
        stem="What is 2+2?",
        status=Question.Status.APPROVED,
    )
    correct = QuestionChoice.objects.create(question=q, label="A", text="4", is_correct=True)
    QuestionChoice.objects.create(question=q, label="B", text="5", is_correct=False)
    return q, correct


@pytest.fixture
def numeric_question(db, topic):
    from decimal import Decimal

    return Question.objects.create(
        topic=topic,
        difficulty=Question.Difficulty.EASY,
        question_type=Question.QuestionType.NUMERIC,
        stem="What is sqrt(9)?",
        correct_answer=Decimal("3"),
        tolerance=Decimal("0.01"),
        status=Question.Status.APPROVED,
    )

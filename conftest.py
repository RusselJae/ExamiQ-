import pytest
from django.contrib.auth import get_user_model

from apps.questions.models import Question, QuestionChoice, Subject, Topic, YearLevel
from apps.users.constants import PROGRAM_DEFINITIONS
from apps.users.models import Course, Department, Program

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
def student(db, department, year_level):
    return User.objects.create_user(
        email="student@test.edu",
        password="testpass123",
        role=User.Role.STUDENT,
        department=department,
        home_degree_program=User.HomeDegreeProgram.CS,
        year_level=year_level,
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

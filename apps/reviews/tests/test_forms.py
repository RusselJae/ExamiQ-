import pytest

from apps.questions.models import Question, QuestionChoice, Subject, Topic
from apps.reviews.exam_setup_services import (
    MIN_EXAM_SUBJECTS,
    QUESTIONS_PER_SUBJECT,
    build_multi_subject_exam_target,
)
from apps.reviews.forms import ReviewSetupForm
from apps.users.models import Program, User
from conftest import make_bsed_student


def _make_subject_with_questions(bsed_program, year_level, code, *, count=3, difficulty=None):
    difficulty = difficulty or Question.Difficulty.EASY
    subject = Subject.objects.create(
        program=bsed_program,
        code=code,
        name=f"Subject {code}",
        year_level=year_level,
        semester=1,
    )
    topic = Topic.objects.create(subject=subject, name=f"Topic {code}")
    for i in range(count):
        q = Question.objects.create(
            topic=topic,
            difficulty=difficulty,
            question_type=Question.QuestionType.MCQ,
            stem=f"{code} Q{i}",
            status=Question.Status.APPROVED,
        )
        QuestionChoice.objects.create(question=q, label="A", text="ok", is_correct=True)
        QuestionChoice.objects.create(question=q, label="B", text="no", is_correct=False)
    return subject


@pytest.mark.django_db
class TestReviewSetupForm:
    def test_lists_all_bsed_subjects_when_student_is_bsed(
        self, student, bsed_program, subject, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)

        other_prog = Program.objects.get_or_create(
            slug=User.HomeDegreeProgram.IT,
            defaults={
                "name": "Information Technology",
                "managing_department": bsed_program.managing_department,
            },
        )[0]
        Subject.objects.create(
            program=other_prog,
            code="IT-101",
            name="IT Subject",
            year_level=year_level,
            semester=1,
        )

        form = ReviewSetupForm(student=student)
        subject_ids = set(form.fields["subjects"].queryset.values_list("pk", flat=True))
        assert subject.pk in subject_ids
        assert form.fields["subjects"].queryset.filter(code="IT-101").count() == 0

    def test_rejects_setup_when_no_subjects_selected(
        self, student, subject, topic, mcq_question, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)

        form = ReviewSetupForm(
            data={
                "subjects": [],
                "difficulty": Question.Difficulty.EASY,
            },
            student=student,
        )
        assert not form.is_valid()
        err = str(form.errors).lower()
        assert "subjects" in form.errors or f"at least {MIN_EXAM_SUBJECTS}" in err

    def test_accepts_setup_with_one_subject(
        self, student, subject, topic, mcq_question, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        # Ensure enough questions for one subject
        for i in range(QUESTIONS_PER_SUBJECT - 1):
            q = Question.objects.create(
                topic=topic,
                difficulty=Question.Difficulty.EASY,
                question_type=Question.QuestionType.MCQ,
                stem=f"Extra {i}",
                status=Question.Status.APPROVED,
            )
            QuestionChoice.objects.create(question=q, label="A", text="ok", is_correct=True)
            QuestionChoice.objects.create(question=q, label="B", text="no", is_correct=False)

        form = ReviewSetupForm(
            data={
                "subjects": [subject.pk],
                "difficulty": Question.Difficulty.EASY,
            },
            student=student,
        )
        assert form.is_valid(), form.errors

    def test_rejects_setup_when_no_questions_available(
        self, student, subject, topic, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        s2 = Subject.objects.create(
            program=bsed_program,
            code="EMPTY-2",
            name="Empty 2",
            year_level=year_level,
            semester=1,
        )
        Topic.objects.create(subject=s2, name="T2")
        s3 = Subject.objects.create(
            program=bsed_program,
            code="EMPTY-3",
            name="Empty 3",
            year_level=year_level,
            semester=1,
        )
        Topic.objects.create(subject=s3, name="T3")

        form = ReviewSetupForm(
            data={
                "subjects": [subject.pk, s2.pk, s3.pk],
                "difficulty": Question.Difficulty.EASY,
            },
            student=student,
        )
        assert not form.is_valid()
        assert "No approved questions" in str(form.errors)

    def test_accepts_multi_subject_setup_when_questions_available(
        self, student, bsed_program, year_level, course
    ):
        make_bsed_student(student, bsed_program=bsed_program, course=course)
        s1 = _make_subject_with_questions(bsed_program, year_level, "MS-1", count=2)
        s2 = _make_subject_with_questions(bsed_program, year_level, "MS-2", count=2)
        s3 = _make_subject_with_questions(bsed_program, year_level, "MS-3", count=2)
        s1.code = course.code
        s1.save(update_fields=["code"])

        form = ReviewSetupForm(
            data={
                "subjects": [s1.pk, s2.pk, s3.pk],
                "difficulty": Question.Difficulty.EASY,
            },
            student=student,
        )
        assert form.is_valid(), form.errors
        target = form.get_auto_target()
        assert target["difficulty"] == Question.Difficulty.EASY
        assert len(target["subjects"]) == 3
        assert len(target["question_queue"]) == 6
        assert target["question_count"] == 6


@pytest.mark.django_db
class TestMultiSubjectQueue:
    def test_caps_questions_per_subject(self, student, bsed_program, year_level):
        make_bsed_student(student, bsed_program=bsed_program)
        subjects = [
            _make_subject_with_questions(
                bsed_program, year_level, f"CAP-{i}", count=15
            )
            for i in range(3)
        ]
        target = build_multi_subject_exam_target(
            student, subjects, Question.Difficulty.EASY
        )
        assert len(target["question_queue"]) == QUESTIONS_PER_SUBJECT * 3

    def test_queue_includes_ids_from_each_subject(
        self, student, bsed_program, year_level
    ):
        make_bsed_student(student, bsed_program=bsed_program)
        subjects = [
            _make_subject_with_questions(bsed_program, year_level, f"MIX-{i}", count=3)
            for i in range(3)
        ]
        target = build_multi_subject_exam_target(
            student, subjects, Question.Difficulty.EASY
        )
        codes = set(
            Question.objects.filter(pk__in=target["question_queue"]).values_list(
                "topic__subject__code", flat=True
            )
        )
        assert codes == {s.code for s in subjects}

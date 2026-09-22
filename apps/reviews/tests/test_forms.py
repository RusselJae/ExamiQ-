import pytest

from apps.questions.models import Question, QuestionChoice, Subject, Topic, YearLevel
from apps.reviews.exam_setup_services import (
    MAX_QUESTIONS_SINGLE_SUBJECT,
    MAX_TOTAL_QUESTIONS,
    MIN_QUESTIONS_PER_SUBJECT,
    build_multi_subject_exam_target,
    other_subjects_available_for_student,
    subjects_available_for_student,
)
from apps.reviews.forms import ReviewSetupForm
from apps.users.models import Program, User
from conftest import make_bsed_student


def _setup_data(student, *, difficulty=None, extra_subjects=None, year_subjects=None):
    """Build valid ReviewSetupForm POST data with year subjects selected."""
    difficulty = difficulty or Question.Difficulty.EASY
    if year_subjects is None:
        year_subjects = list(
            subjects_available_for_student(student).values_list("pk", flat=True)
        )
    data = {
        "difficulty": difficulty,
        "question_type": [Question.QuestionType.MCQ],
        "year_subjects": year_subjects,
    }
    if extra_subjects is not None:
        data["extra_subjects"] = extra_subjects
    return data


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
    def test_year_subjects_exclude_other_programs_and_years(
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
        other_year, _ = YearLevel.objects.get_or_create(
            order=99, defaults={"name": "Other Year"}
        )
        Subject.objects.create(
            program=bsed_program,
            code="Y2-101",
            name="Year Two",
            year_level=other_year,
            semester=1,
        )

        form = ReviewSetupForm(student=student)
        codes = {s.code for s in form.year_subjects}
        assert subject.code in codes
        assert "IT-101" not in codes
        assert "Y2-101" not in codes
        assert "subjects" not in form.fields

    def test_rejects_setup_when_student_has_no_year_level(
        self, student, subject, topic, mcq_question, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        student.year_level = None
        student.save(update_fields=["year_level"])

        form = ReviewSetupForm(
            data=_setup_data(student),
            student=student,
        )
        assert not form.is_valid()
        assert "year level" in str(form.errors).lower()

    def test_accepts_setup_with_year_subjects(
        self, student, subject, topic, mcq_question, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        for i in range(MIN_QUESTIONS_PER_SUBJECT - 1):
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
            data=_setup_data(student),
            student=student,
        )
        assert form.is_valid(), form.errors
        assert subject in form.get_auto_target()["subjects"]

    def test_rejects_setup_when_no_questions_available(
        self, student, subject, topic, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        Subject.objects.create(
            program=bsed_program,
            code="EMPTY-2",
            name="Empty 2",
            year_level=year_level,
            semester=1,
        )

        form = ReviewSetupForm(
            data=_setup_data(student),
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
            data=_setup_data(student),
            student=student,
        )
        assert form.is_valid(), form.errors
        target = form.get_auto_target()
        assert target["difficulty"] == Question.Difficulty.EASY
        assert len(target["subjects"]) == 3
        assert len(target["question_queue"]) == 6
        assert target["question_count"] == 6

    def test_accepts_optional_extra_subjects_from_other_years(
        self, student, bsed_program, year_level, course
    ):
        make_bsed_student(student, bsed_program=bsed_program, course=course)
        year_subj = _make_subject_with_questions(
            bsed_program, year_level, "Y1-FILL", count=3
        )
        year_subj.code = course.code
        year_subj.save(update_fields=["code"])
        other_year, _ = YearLevel.objects.get_or_create(
            order=97, defaults={"name": "Year 97"}
        )
        other = _make_subject_with_questions(
            bsed_program, other_year, "Y97-EXTRA", count=3
        )

        form = ReviewSetupForm(
            data=_setup_data(student, extra_subjects=[other.pk]),
            student=student,
        )
        assert form.is_valid(), form.errors
        codes = {s.code for s in form.get_auto_target()["subjects"]}
        assert codes == {course.code, "Y97-EXTRA"}

    def test_allows_unselecting_some_year_subjects(
        self, student, bsed_program, year_level, course
    ):
        make_bsed_student(student, bsed_program=bsed_program, course=course)
        keep = _make_subject_with_questions(bsed_program, year_level, "KEEP-Y", count=3)
        keep.code = course.code
        keep.save(update_fields=["code"])
        drop = _make_subject_with_questions(bsed_program, year_level, "DROP-Y", count=3)

        form = ReviewSetupForm(
            data=_setup_data(student, year_subjects=[keep.pk]),
            student=student,
        )
        assert form.is_valid(), form.errors
        codes = {s.code for s in form.get_auto_target()["subjects"]}
        assert codes == {course.code}
        assert drop.code not in codes

    def test_defaults_to_year_subjects_when_extra_empty(
        self, student, bsed_program, year_level, course
    ):
        make_bsed_student(student, bsed_program=bsed_program, course=course)
        year_subj = _make_subject_with_questions(
            bsed_program, year_level, "Y1-ONLY", count=3
        )
        year_subj.code = course.code
        year_subj.save(update_fields=["code"])
        other_year, _ = YearLevel.objects.get_or_create(
            order=96, defaults={"name": "Year 96"}
        )
        _make_subject_with_questions(bsed_program, other_year, "Y96-SKIP", count=3)

        form = ReviewSetupForm(
            data=_setup_data(student),
            student=student,
        )
        assert form.is_valid(), form.errors
        codes = {s.code for s in form.get_auto_target()["subjects"]}
        assert codes == {course.code}

    def test_skips_empty_year_subjects_when_building_exam(
        self, student, bsed_program, year_level, course
    ):
        make_bsed_student(student, bsed_program=bsed_program, course=course)
        _make_subject_with_questions(bsed_program, year_level, "FILL-1", count=3)
        Subject.objects.create(
            program=bsed_program,
            code="EMPTY-Y",
            name="Empty Year Subject",
            year_level=year_level,
            semester=1,
        )

        form = ReviewSetupForm(
            data=_setup_data(student),
            student=student,
        )
        assert form.is_valid(), form.errors
        assert [s.code for s in form.get_auto_target()["subjects"]] == ["FILL-1"]

    def test_mcq_only_excludes_other_question_types(
        self, student, subject, topic, mcq_question, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        for i in range(MIN_QUESTIONS_PER_SUBJECT - 1):
            q = Question.objects.create(
                topic=topic,
                difficulty=Question.Difficulty.EASY,
                question_type=Question.QuestionType.MCQ,
                stem=f"Extra MCQ {i}",
                status=Question.Status.APPROVED,
            )
            QuestionChoice.objects.create(question=q, label="A", text="ok", is_correct=True)
            QuestionChoice.objects.create(question=q, label="B", text="no", is_correct=False)
        Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.TRUE_FALSE,
            stem="TF question",
            expected_answer="True",
            status=Question.Status.APPROVED,
        )

        form = ReviewSetupForm(
            data=_setup_data(student),
            student=student,
        )
        assert form.is_valid(), form.errors
        queue = form.get_auto_target()["question_queue"]
        types = set(
            Question.objects.filter(pk__in=queue).values_list("question_type", flat=True)
        )
        assert types == {Question.QuestionType.MCQ}

    def test_rejects_when_no_questions_for_selected_type(
        self, student, subject, topic, bsed_program, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.TRUE_FALSE,
            stem="TF only",
            expected_answer="True",
            status=Question.Status.APPROVED,
        )

        form = ReviewSetupForm(
            data=_setup_data(student),
            student=student,
        )
        assert not form.is_valid()
        err = str(form.errors)
        assert "No approved questions" in err


@pytest.mark.django_db
class TestSubjectsAvailableForStudent:
    def test_filters_to_student_year_level(
        self, student, bsed_program, subject, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        other_year, _ = YearLevel.objects.get_or_create(
            order=98, defaults={"name": "Year 98"}
        )
        Subject.objects.create(
            program=bsed_program,
            code="OTH-Y",
            name="Other Year Subject",
            year_level=other_year,
            semester=1,
        )
        qs = subjects_available_for_student(student)
        assert subject.pk in qs.values_list("pk", flat=True)
        assert not qs.filter(code="OTH-Y").exists()

    def test_empty_without_year_level(self, student, subject, bsed_program):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        student.year_level = None
        student.save(update_fields=["year_level"])
        assert not subjects_available_for_student(student).exists()
        assert not other_subjects_available_for_student(student).exists()

    def test_other_subjects_are_outside_student_year(
        self, student, bsed_program, subject, year_level
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        other_year, _ = YearLevel.objects.get_or_create(
            order=95, defaults={"name": "Year 95"}
        )
        Subject.objects.create(
            program=bsed_program,
            code="OUT-Y",
            name="Outside Year",
            year_level=other_year,
            semester=1,
        )
        other = other_subjects_available_for_student(student)
        assert other.filter(code="OUT-Y").exists()
        assert not other.filter(pk=subject.pk).exists()


@pytest.mark.django_db
class TestMultiSubjectQueue:
    def test_each_subject_gets_minimum_questions(self, student, bsed_program, year_level):
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
        queue = target["question_queue"]
        assert len(queue) >= MIN_QUESTIONS_PER_SUBJECT * len(subjects)
        assert target["question_count"] == len(queue)

    def test_single_subject_capped_at_20(self, student, bsed_program, year_level):
        make_bsed_student(student, bsed_program=bsed_program)
        subject = _make_subject_with_questions(
            bsed_program, year_level, "SINGLE-25", count=25
        )
        target = build_multi_subject_exam_target(
            student, [subject], Question.Difficulty.EASY
        )
        count = target["question_count"]
        assert MIN_QUESTIONS_PER_SUBJECT <= count <= MAX_QUESTIONS_SINGLE_SUBJECT
        assert len(target["question_queue"]) == count

    def test_many_subjects_capped_at_max_total(self, student, bsed_program, year_level):
        make_bsed_student(student, bsed_program=bsed_program)
        subjects = [
            _make_subject_with_questions(
                bsed_program, year_level, f"MANY-{i}", count=15
            )
            for i in range(13)
        ]
        target = build_multi_subject_exam_target(
            student, subjects, Question.Difficulty.EASY
        )
        assert target["question_count"] == MAX_TOTAL_QUESTIONS
        codes = set(
            Question.objects.filter(pk__in=target["question_queue"]).values_list(
                "topic__subject__code", flat=True
            )
        )
        assert len(codes) == 13

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

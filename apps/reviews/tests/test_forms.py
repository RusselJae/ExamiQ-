import pytest

from apps.questions.models import Question, Subject
from apps.reviews.forms import ReviewSetupForm
from apps.reviews.models import ExamSetup
from apps.users.models import Program, User


@pytest.mark.django_db
class TestReviewSetupForm:
    def test_filters_subjects_by_enabled_assignment(
        self, student, program, subject, teaching_assignment
    ):
        other_prog = Program.objects.get(slug=User.HomeDegreeProgram.IT)
        Subject.objects.create(
            program=other_prog,
            code="IT-101",
            name="IT Subject",
            year_level=subject.year_level,
            semester=1,
        )

        form = ReviewSetupForm(student=student)
        subject_ids = set(form.fields["subject"].queryset.values_list("pk", flat=True))
        assert subject_ids == {subject.pk}

    def test_empty_subjects_when_no_enabled_assignment(self, student, subject):
        form = ReviewSetupForm(student=student)
        assert form.fields["subject"].queryset.count() == 0

    def test_empty_subjects_when_exam_setup_disabled(
        self, student, subject, teaching_assignment
    ):
        setup = ExamSetup.objects.get(course=teaching_assignment.course)
        setup.is_enabled = False
        setup.save(update_fields=["is_enabled"])
        form = ReviewSetupForm(student=student)
        assert form.fields["subject"].queryset.count() == 0

    def test_rejects_setup_when_no_questions_available(
        self, student, subject, topic, teaching_assignment
    ):
        form = ReviewSetupForm(
            data={
                "subject": subject.pk,
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
            },
            student=student,
        )
        assert not form.is_valid()
        assert "No approved questions" in str(form.non_field_errors())

    def test_accepts_setup_when_questions_available(
        self, student, subject, topic, mcq_question, teaching_assignment
    ):
        form = ReviewSetupForm(
            data={
                "subject": subject.pk,
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
            },
            student=student,
        )
        assert form.is_valid(), form.errors

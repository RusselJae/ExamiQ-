import pytest

from apps.questions.models import Question, Subject
from apps.reviews.forms import ReviewSetupForm
from apps.users.models import Program, User


@pytest.mark.django_db
class TestReviewSetupForm:
    def test_filters_subjects_by_student_home_program(self, student, program, subject):
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

    def test_empty_subjects_when_home_program_unset(self, db, professor, program, subject):
        student = User.objects.create_user(
            email="noprog@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
        )
        form = ReviewSetupForm(student=student)
        assert form.fields["subject"].queryset.count() == 0

    def test_rejects_setup_when_no_questions_available(self, student, subject, topic):
        form = ReviewSetupForm(
            data={
                "subject": subject.pk,
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "duration_minutes": 30,
            },
            student=student,
        )
        assert not form.is_valid()
        assert "No approved questions" in str(form.non_field_errors())

    def test_accepts_setup_when_questions_available(self, student, subject, topic, mcq_question):
        form = ReviewSetupForm(
            data={
                "subject": subject.pk,
                "topic": topic.pk,
                "difficulty": Question.Difficulty.EASY,
                "duration_minutes": 30,
            },
            student=student,
        )
        assert form.is_valid(), form.errors

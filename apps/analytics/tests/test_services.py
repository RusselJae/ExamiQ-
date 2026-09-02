import pytest

from apps.analytics.services import course_performance_summary, student_performance_summary
from apps.users.models import Course


@pytest.mark.django_db
class TestAnalyticsServices:
    def test_student_performance_summary_empty(self, student):
        summary = student_performance_summary(student)
        assert summary["sessions_completed"] == 0
        assert summary["accuracy"] == 0.0

    def test_course_performance_summary(self, student, professor, program, topic):
        course = Course.objects.create(
            program=program,
            code="M101",
            name="Math",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="B",
        )
        from apps.reviews.models import ReviewSession

        ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty="easy",
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        summary = course_performance_summary(course)
        assert summary["enrolled_count"] == 1

    def test_course_confidence_mapped_to_zero_three_scale(
        self, student, professor, program, topic, mcq_question
    ):
        from apps.reviews.models import Answer, ReviewSession

        question, _ = mcq_question
        course = Course.objects.create(
            program=program,
            code="CONF101",
            name="Confidence Course",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="B",
        )
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty="easy",
            course=course,
            status=ReviewSession.Status.COMPLETED,
        )
        Answer.objects.create(
            session=session, question=question, confidence=5, is_correct=True
        )
        summary = course_performance_summary(course)
        row = summary["confidence_by_topic"][0]
        assert row["avg_confidence"] == 3.0

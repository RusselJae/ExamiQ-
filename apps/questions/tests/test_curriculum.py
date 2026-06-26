import pytest
from django.urls import reverse

from apps.questions.curriculum import get_subjects_for_professor
from apps.questions.models import Question, Subject, YearLevel
from apps.questions.services import count_available_questions


@pytest.mark.django_db
class TestCurriculumHelpers:
    def test_count_available_questions(self, topic, mcq_question):
        assert count_available_questions(topic, Question.Difficulty.EASY) == 1
        assert count_available_questions(topic, Question.Difficulty.MEDIUM) == 0

    def test_get_subjects_for_professor_falls_back_when_year_empty(self, program, year_level):
        year3, _ = YearLevel.objects.get_or_create(order=3, defaults={"name": "3rd Year"})
        year1, _ = YearLevel.objects.get_or_create(order=1, defaults={"name": "1st Year"})
        Subject.objects.create(
            program=program,
            code="COSC 50",
            name="Discrete Structures I",
            year_level=year1,
            semester=1,
        )
        subjects = get_subjects_for_professor(program.pk, year3.pk)
        assert subjects.filter(code="COSC 50").exists()

    def test_get_subjects_for_professor_filters_by_year_when_present(self, program, year_level, subject):
        year1, _ = YearLevel.objects.get_or_create(order=1, defaults={"name": "1st Year"})
        Subject.objects.create(
            program=program,
            code="COSC 50",
            name="Discrete Structures I",
            year_level=year1,
            semester=1,
        )
        subjects = get_subjects_for_professor(program.pk, year_level.pk)
        assert subjects.filter(code="TEST-101").exists()
        assert not subjects.filter(code="COSC 50").exists()


@pytest.mark.django_db
class TestProfessorCurriculumSubjectsView:
    def test_cs_subjects_fallback_when_year_has_none(self, client, professor, course, program):
        year3, _ = YearLevel.objects.get_or_create(order=3, defaults={"name": "3rd Year"})
        year1, _ = YearLevel.objects.get_or_create(order=1, defaults={"name": "1st Year"})
        Subject.objects.create(
            program=program,
            code="COSC 55",
            name="Discrete Structures II",
            year_level=year1,
            semester=1,
        )
        client.force_login(professor)
        url = reverse("analytics_professor:curriculum_subjects", kwargs={"course_pk": course.pk})
        response = client.get(url, {"program": program.pk, "year_level": year3.pk})
        data = response.json()

        codes = {s["code"] for s in data["subjects"]}
        assert "COSC 55" in codes
        assert data["fallback_message"]

    def test_cs_subjects_filtered_by_year(self, client, professor, course, program, year_level, subject):
        year1, _ = YearLevel.objects.get_or_create(order=1, defaults={"name": "1st Year"})
        Subject.objects.create(
            program=program,
            code="COSC 55",
            name="Discrete Structures II",
            year_level=year1,
            semester=1,
        )
        client.force_login(professor)
        url = reverse("analytics_professor:curriculum_subjects", kwargs={"course_pk": course.pk})
        response = client.get(url, {"program": program.pk, "year_level": year_level.pk})
        data = response.json()

        codes = {s["code"] for s in data["subjects"]}
        assert codes == {"TEST-101"}
        assert data["fallback_message"] == ""


@pytest.mark.django_db
class TestProfessorCurriculumTopicsView:
    def test_returns_topics_for_subject(self, client, professor, course, subject, topic):
        client.force_login(professor)
        url = reverse("analytics_professor:curriculum_topics", kwargs={"course_pk": course.pk})
        response = client.get(url, {"subject": subject.pk})

        assert response.status_code == 200
        data = response.json()
        assert data["topics"] == [{"id": topic.pk, "name": topic.name}]

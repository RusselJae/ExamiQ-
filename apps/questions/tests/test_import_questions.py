import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.questions.import_services import ImportFormatError, import_questions_from_csv
from apps.questions.models import ExplanationStep, Question


CSV_HEADER = (
    "subject_code,topic_name,difficulty,question_type,stem,"
    "choice_a,choice_b,choice_c,choice_d,correct_label,expected_answer,"
    "concept_tag,explanation_step_1,explanation_step_2,explanation_step_3,"
    "status,is_active\n"
)


def _csv_file(*rows: str) -> SimpleUploadedFile:
    content = CSV_HEADER + "".join(rows)
    return SimpleUploadedFile(
        "questions.csv",
        content.encode("utf-8"),
        content_type="text/csv",
    )


@pytest.fixture
def course_with_subject(course, subject):
    subject.code = course.code
    subject.save(update_fields=["code"])
    return course


@pytest.mark.django_db
class TestImportQuestionsFromCsv:
    def test_imports_mcq_rows_only(self, professor, subject, topic):
        subject.code = "BSEM 22"
        subject.save(update_fields=["code"])
        topic.name = "College and Advanced Algebra"
        topic.save(update_fields=["name"])

        uploaded = _csv_file(
            "BSEM 22,College and Advanced Algebra,easy,mcq,Solve 2x + 7 = 15?,x=3,x=4,x=5,x=6,B,,Linear,Subtract 7.,Divide by 2.,,approved,true\n",
            "BSEM 22,College and Advanced Algebra,easy,true_false,The empty set is a subset of every set.,,,,,,TRUE,Sets,By definition.,,approved,true\n",
        )

        summary = import_questions_from_csv(
            uploaded,
            subject=subject,
            professor=professor,
        )

        assert summary.created == 1
        assert summary.skipped_invalid >= 1
        assert Question.objects.filter(topic=topic).count() == 1
        q = Question.objects.get(topic=topic)
        assert q.question_type == Question.QuestionType.MCQ
        assert ExplanationStep.objects.filter(question=q).count() >= 1

    def test_rejects_wrong_subject_code(self, professor, subject, topic):
        subject.code = "BSEM 22"
        subject.save(update_fields=["code"])
        uploaded = _csv_file(
            "BSEM 23,Algebra,easy,mcq,What is 2+2?,3,4,5,6,B,,Tag,Step,,,approved,true\n",
        )

        summary = import_questions_from_csv(
            uploaded, subject=subject, professor=professor
        )

        assert summary.created == 0
        assert summary.skipped_invalid == 1
        assert "subject_code" in summary.row_errors[0].message

    def test_skips_duplicate_stem(self, professor, subject, topic):
        subject.code = "T101"
        subject.save(update_fields=["code"])
        uploaded = _csv_file(
            "T101,Algebra,easy,mcq,What is 2+2?,3,4,5,6,B,,Tag,Step,,,approved,true\n",
            "T101,Algebra,easy,mcq,What is 2+2?,3,4,5,6,B,,Tag,Step,,,approved,true\n",
        )

        summary = import_questions_from_csv(
            uploaded, subject=subject, professor=professor
        )

        assert summary.created == 1
        assert summary.skipped_duplicates == 1

    def test_raises_on_missing_headers(self, professor, subject):
        uploaded = SimpleUploadedFile(
            "bad.csv",
            b"stem,choice_a\nWhat?,A\n",
            content_type="text/csv",
        )
        with pytest.raises(ImportFormatError, match="Missing required column"):
            import_questions_from_csv(uploaded, subject=subject, professor=professor)


@pytest.mark.django_db
class TestQuestionCSVImportView:
    def test_import_view_creates_questions(
        self, client, professor, course_with_subject, topic
    ):
        client.force_login(professor)
        uploaded = _csv_file(
            f"{course_with_subject.code},Algebra,easy,mcq,Imported question?,1,2,3,4,B,,Tag,Step one.,,,approved,true\n",
        )
        url = reverse(
            "analytics_professor:question_csv_import",
            kwargs={"course_pk": course_with_subject.pk},
        )
        response = client.post(url, {"csv_file": uploaded})

        assert response.status_code == 200
        payload = response.json()
        assert payload["created"] == 1
        assert Question.objects.filter(stem="Imported question?").exists()

    def test_import_view_requires_file(self, client, professor, course_with_subject):
        client.force_login(professor)
        url = reverse(
            "analytics_professor:question_csv_import",
            kwargs={"course_pk": course_with_subject.pk},
        )
        response = client.post(url)
        assert response.status_code == 400
        assert "CSV" in response.json()["error"]

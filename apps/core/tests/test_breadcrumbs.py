"""Tests for navbar breadcrumb labels and trails."""

from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.breadcrumbs import build_nav_breadcrumbs, humanize_url_name
from apps.users.models import Course


@pytest.mark.parametrize(
    "url_name,expected",
    [
        ("student_detail", "Student Detail"),
        ("question_list", "Saved Questions"),
        ("question_create", "Add Question"),
        ("question_add", "Add Question"),
        ("session_history", "Session History"),
        ("unknown_thing_here", "Unknown Thing Here"),
    ],
)
def test_humanize_url_name_uses_spaces(url_name, expected):
    assert humanize_url_name(url_name) == expected
    assert " " in expected or expected == url_name.replace("_", " ").title()
    assert "Studentdetail" not in humanize_url_name("student_detail")
    assert "Questionlist" not in humanize_url_name("question_list")
    assert "Questionadd" not in humanize_url_name("question_add")


@pytest.mark.django_db
class TestBuildNavBreadcrumbs:
    def test_home_only_when_unauthenticated(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=False)
        request.resolver_match = SimpleNamespace(
            url_name="home", namespace="core", kwargs={}
        )
        crumbs = build_nav_breadcrumbs(request)
        assert [c["label"] for c in crumbs] == ["Home"]

    def test_professor_question_list_trail(self, professor, program):
        course = Course.objects.create(
            program=program,
            code="GNED 03",
            name="Mathematics in the Modern World",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="Catalog",
        )
        request = RequestFactory().get(
            reverse("analytics_professor:question_list", kwargs={"course_pk": course.pk})
        )
        request.user = professor
        request.resolver_match = SimpleNamespace(
            url_name="question_list",
            namespace="analytics_professor",
            kwargs={"course_pk": course.pk},
        )
        labels = [c["label"] for c in build_nav_breadcrumbs(request)]
        assert labels[0] == "Home"
        assert "Courses" in labels
        # Course code and page label are combined into a single crumb.
        assert "GNED 03 - Saved Questions" in labels
        assert "GNED 03" not in labels
        assert "Saved Questions" not in labels
        assert "Questionlist" not in "".join(labels)

    def test_professor_add_question_trail(self, professor, program):
        course = Course.objects.create(
            program=program,
            code="GNED 03",
            name="Math",
            professor=professor,
            term="1st Sem",
            academic_year="2026",
            section="A",
        )
        request = RequestFactory().get(
            reverse(
                "analytics_professor:question_create",
                kwargs={"course_pk": course.pk},
            )
        )
        request.user = professor
        request.resolver_match = SimpleNamespace(
            url_name="question_create",
            namespace="analytics_professor",
            kwargs={"course_pk": course.pk},
        )
        labels = [c["label"] for c in build_nav_breadcrumbs(request)]
        assert "GNED 03 - Add Question" in labels
        assert "Saved Questions" not in labels
        assert labels[-1] == "GNED 03 - Add Question"
        assert "Questionadd" not in "".join(labels)

    def test_student_concepts_tab_trail(self, student):
        request = RequestFactory().get(
            reverse("analytics_student:mistakes") + "?tab=concepts"
        )
        request.user = student
        request.resolver_match = SimpleNamespace(
            url_name="mistakes",
            namespace="analytics_student",
            kwargs={},
        )
        labels = [c["label"] for c in build_nav_breadcrumbs(request)]
        assert labels == ["Home", "Action Plan", "Concepts to Review"]

    def test_student_detail_label_has_space(self, professor):
        request = RequestFactory().get("/professor/students/1/")
        request.user = professor
        request.resolver_match = SimpleNamespace(
            url_name="professor_student_detail",
            namespace="analytics_professor",
            kwargs={"pk": 1},
        )
        labels = [c["label"] for c in build_nav_breadcrumbs(request)]
        assert "Student Detail" in labels
        assert "Studentdetail" not in "".join(labels)


@pytest.mark.django_db
class TestQuestionListHeaderCta:
    def test_add_question_button_on_header_row(self, client, professor, course):
        client.force_login(professor)
        response = client.get(
            reverse("analytics_professor:question_list", kwargs={"course_pk": course.pk})
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Add Question" in content
        # CTA lives in the overview header aside, not a separate justify-end row.
        assert "overview-header__aside" in content
        assert 'class="btn-primary btn-primary-sm"' in content
        assert "flex justify-end items-center mb-4" not in content

"""Learning materials list, download, and student library."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.ai.ingest import ingest_learning_upload
from apps.ai.models import LearningDocument
from apps.ai.source_extract import SourceMaterialError
from apps.reviews.exam_setup_services import sync_program_subject_timers
from apps.users.assignment_services import get_or_create_catalog_course
from conftest import make_bsed_student


def _make_ready_doc(*, course, subject, user, title="Module overview", archived=False):
    doc = LearningDocument.objects.create(
        course_id=course.pk,
        subject=subject,
        created_by=user,
        title=title,
        original_name=f"{title}.txt",
        material_type=LearningDocument.MaterialType.MODULE,
        status=LearningDocument.Status.READY,
        page_count=1,
        chunk_count=1,
        is_archived=archived,
    )
    doc.file.save(f"{title}.txt", ContentFile(b"Sample module content."), save=True)
    return doc


@pytest.mark.django_db
class TestFacultyMaterialsUI:
    def test_list_redirects_to_hub_with_subject(
        self, client, professor, subject
    ):
        course = get_or_create_catalog_course(professor, subject)
        _make_ready_doc(course=course, subject=subject, user=professor)

        client.force_login(professor)
        response = client.get(
            reverse("analytics_professor:material_list", kwargs={"course_pk": course.pk})
        )
        assert response.status_code == 302
        assert reverse("analytics_professor:materials_hub") in response.url
        assert f"subject={subject.pk}" in response.url

    def test_hub_with_subject_shows_edit_not_download(
        self, client, professor, subject, bsed_program
    ):
        subject.program = bsed_program
        subject.save(update_fields=["program"])
        course = get_or_create_catalog_course(professor, subject)
        _make_ready_doc(course=course, subject=subject, user=professor)

        client.force_login(professor)
        response = client.get(
            reverse("analytics_professor:materials_hub") + f"?subject={subject.pk}"
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "materials-library" in content
        assert ">Edit</a>" in content
        assert "Archive" in content
        # Faculty library should not expose Download as the primary action.
        assert 'class="materials-download-btn">Download</a>' not in content

    def test_download_returns_attachment(self, client, professor, subject):
        course = get_or_create_catalog_course(professor, subject)
        doc = _make_ready_doc(course=course, subject=subject, user=professor)

        client.force_login(professor)
        response = client.get(
            reverse(
                "analytics_professor:material_download",
                kwargs={"course_pk": course.pk, "pk": doc.pk},
            )
        )
        assert response.status_code == 200
        assert response["Content-Disposition"].startswith("attachment;")
        assert b"Sample module content." in b"".join(response.streaming_content)

    def test_archive_from_list_hides_from_students(
        self, client, professor, student, subject, bsed_program
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        sync_program_subject_timers(
            bsed_program,
            subject_ids=[subject.pk],
            timers_by_subject_id={subject.pk: 30},
            default_seconds=30,
        )
        course = get_or_create_catalog_course(professor, subject)
        doc = _make_ready_doc(course=course, subject=subject, user=professor)

        client.force_login(professor)
        archive = client.post(
            reverse(
                "analytics_professor:material_detail",
                kwargs={"course_pk": course.pk, "pk": doc.pk},
            ),
            {"action": "archive"},
        )
        assert archive.status_code == 302
        doc.refresh_from_db()
        assert doc.is_archived is True

        client.force_login(student)
        listing = client.get(
            reverse(
                "analytics_student:materials_list",
                kwargs={"subject_pk": subject.pk},
            )
        )
        content = listing.content.decode()
        assert doc.display_title not in content
        download = client.get(
            reverse(
                "analytics_student:materials_download",
                kwargs={"subject_pk": subject.pk, "pk": doc.pk},
            )
        )
        assert download.status_code == 404


@pytest.mark.django_db
class TestStudentMaterials:
    def test_hub_and_subject_library_with_download(
        self, client, student, professor, subject, bsed_program
    ):
        make_bsed_student(student, subject=subject, bsed_program=bsed_program)
        sync_program_subject_timers(
            bsed_program,
            subject_ids=[subject.pk],
            timers_by_subject_id={subject.pk: 30},
            default_seconds=30,
        )
        course = get_or_create_catalog_course(professor, subject)
        doc = _make_ready_doc(course=course, subject=subject, user=professor)

        client.force_login(student)
        hub = client.get(reverse("analytics_student:materials_hub"))
        hub_content = hub.content.decode()
        assert hub.status_code == 200
        assert subject.code in hub_content
        assert "Learning materials" in hub_content
        # Table layout matching faculty course subjects, with Open action
        assert 'id="materials-subjects-table"' in hub_content
        assert ">Open</a>" in hub_content
        assert "materials-subject-grid" not in hub_content

        listing = client.get(
            reverse(
                "analytics_student:materials_list",
                kwargs={"subject_pk": subject.pk},
            )
        )
        content = listing.content.decode()
        assert listing.status_code == 200
        assert "Download" in content
        assert doc.display_title in content
        assert "Upload material" not in content
        assert "Archive" not in content

        download = client.get(
            reverse(
                "analytics_student:materials_download",
                kwargs={"subject_pk": subject.pk, "pk": doc.pk},
            )
        )
        assert download.status_code == 200
        assert download["Content-Disposition"].startswith("attachment;")


@pytest.mark.django_db
class TestIngestFullFileDownload:
    def test_keeps_full_file_ready_when_text_extraction_fails(self, professor):
        upload = SimpleUploadedFile(
            "module.pdf",
            b"%PDF-1.4 fake binary that will not extract",
            content_type="application/pdf",
        )
        with patch(
            "apps.ai.ingest.extract_pages_from_upload",
            side_effect=SourceMaterialError("Could not extract enough text"),
        ):
            doc = ingest_learning_upload(
                uploaded_file=upload,
                course_id=1,
                user=professor,
            )
        assert doc.status == LearningDocument.Status.READY
        assert doc.file
        assert doc.file.read() == b"%PDF-1.4 fake binary that will not extract"
        assert "Full file saved for download" in doc.error_message

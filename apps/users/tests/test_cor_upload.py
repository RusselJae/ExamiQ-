"""COR upload analysis and the coordinator student-number roster."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.questions.models import Subject, YearLevel
from apps.users.cor_services import (
    CorAnalysisError,
    extract_cor_text,
    match_cor_rows,
    normalize_code,
)
from apps.users.models import (
    AcademicTerm,
    AcademicYear,
    Department,
    PendingStudentRegistration,
    Program,
    User,
)


@pytest.fixture
def catalog_program(db):
    program = _bsed_program()
    year, _ = AcademicYear.objects.get_or_create(label="2025-2026")
    year_level, _ = YearLevel.objects.get_or_create(
        order=1, defaults={"name": "1st Year"}
    )
    return program, year_level, year


def _make_subject(program, year_level, code, name):
    return Subject.objects.create(
        program=program,
        code=code,
        name=name,
        year_level=year_level,
        semester=Subject.Semester.FIRST,
    )


def _bsed_program():
    edu, _ = Department.objects.get_or_create(name="College of Education")
    program, _ = Program.objects.get_or_create(
        slug=User.HomeDegreeProgram.BSED_MATH,
        defaults={"name": "BSEd Mathematics", "managing_department": edu},
    )
    return program


def _term():
    year, _ = AcademicYear.objects.get_or_create(
        label="2025-2026", defaults={"is_current": True}
    )
    term, _ = AcademicTerm.objects.get_or_create(
        academic_year=year,
        name="1st Sem",
        defaults={"is_current": True, "semester": 1},
    )
    return term


@pytest.mark.django_db
class TestCorMatching:
    def test_normalize_code_collapses_punctuation(self):
        assert normalize_code("bsem-21") == "BSEM21"
        assert normalize_code("GE 3") == "GE3"
        assert normalize_code("") == ""

    def test_match_prefers_exact_normalized_code(self, catalog_program):
        program, year_level, _year = catalog_program
        subject = _make_subject(
            program, year_level, "BSEM 21", "History of Mathematics"
        )
        rows = [{"code": "BSEM 21", "title": "anything"}]
        result = match_cor_rows(rows)
        assert [m["subject_id"] for m in result["matched"]] == [subject.id]
        assert result["matched"][0]["confidence"] == "high"

    def test_match_fixes_ocr_transpositions_by_title(self, catalog_program):
        program, year_level, _year = catalog_program
        _make_subject(program, year_level, "BSEM 23", "Trigonometry")
        rows = [{"code": "BSEM 2L", "title": "Trigonometry"}]
        result = match_cor_rows(rows)
        assert len(result["matched"]) == 1
        assert result["matched"][0]["code"] == "BSEM 23"
        assert result["unmatched"] == []

    def test_match_flags_unknown_codes_as_unmatched(self, catalog_program):
        program, year_level, _year = catalog_program
        _make_subject(program, year_level, "BSEM 21", "History of Mathematics")
        rows = [{"code": "XXX 99", "title": "Unknown Course"}]
        result = match_cor_rows(rows)
        assert result["matched"] == []
        assert result["unmatched"] == [{"code": "XXX 99", "title": "Unknown Course"}]

    def test_match_does_not_reuse_one_subject_twice(self, catalog_program):
        program, year_level, _year = catalog_program
        subject = _make_subject(
            program, year_level, "BSEM 21", "History of Mathematics"
        )
        rows = [
            {"code": "BSEM 21", "title": "History of Mathematics"},
            {"code": "BSEM 2l", "title": "History of Mathematics"},
        ]
        result = match_cor_rows(rows)
        assert len(result["matched"]) == 1
        assert result["matched"][0]["subject_id"] == subject.id
        assert len(result["unmatched"]) == 1


@pytest.mark.django_db
class TestCorExtraction:
    def test_unknown_extension_rejected(self):
        file = SimpleUploadedFile("cor.txt", b"hello", content_type="text/plain")
        with pytest.raises(CorAnalysisError):
            extract_cor_text(file)

    def test_empty_image_raises(self):
        file = SimpleUploadedFile("cor.png", b"", content_type="image/png")
        with pytest.raises(CorAnalysisError):
            extract_cor_text(file)

    def test_pdf_extraction_reads_text_layer(self):
        """A text-layer PDF path is exercised via monkeypatched pages."""
        from apps.users import cor_services

        class FakeFile:
            name = "cor.pdf"

            def read(self):
                return b"%PDF-1.4 fake"

        fake_pages = [
            {
                "page": 1,
                "text": "BSEM 21 - History of Mathematics. Still in the extraction test fixture.",
            }
        ]
        from unittest.mock import patch

        with patch.object(
            __import__("apps.ai.source_extract", fromlist=["x"]),
            "extract_pages_from_upload",
            return_value=fake_pages,
        ):
            text = cor_services.extract_cor_text(FakeFile())
        assert "BSEM 21" in text


def _text_layer_pdf(lines):
    ops = ""
    y = 750
    for ln in lines:
        safe = ln.replace("(", "\\(").replace(")", "\\)")
        ops += f"BT /F1 12 Tf 50 {y} Td ({safe}) Tj ET\n"
        y -= 20
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = ops.encode("latin-1")
    objs.append(
        f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
        + stream
        + b"\nendstream"
    )
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(pdf))
        pdf += (
            f"{i} 0 obj\n".encode()
            + (o if isinstance(o, bytes) else o.encode("latin-1"))
            + b"\nendobj\n"
        )
    xref = len(pdf)
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return pdf


@pytest.mark.django_db
def test_real_pdf_end_to_end_analyze(client, bsed_program, year_level):
    from apps.questions.models import Subject

    Subject.objects.create(
        program=bsed_program,
        code="BSEM 21",
        name="History of Mathematics",
        year_level=year_level,
        semester=Subject.Semester.FIRST,
    )
    Subject.objects.create(
        program=bsed_program,
        code="BSEM 22",
        name="College and Advanced Algebra",
        year_level=year_level,
        semester=Subject.Semester.FIRST,
    )
    pdf = _text_layer_pdf(
        [
            "CERTIFICATE OF REGISTRATION",
            "Student Type: Regular",
            "BSEM 21 - History of Mathematics",
            "BSEM 22 - College and Advanced Algebra",
        ]
    )
    f = SimpleUploadedFile("cor.pdf", pdf, content_type="application/pdf")
    r = client.post(reverse("users:cor_analyze"), {"cor_file": f})
    assert r.status_code == 200, r.content[:500]
    data = r.json()
    print("\ncor_type:", data.get("cor_type"))
    print("suggested_year:", data.get("suggested_year_level"))
    print("matched:", [(m["code"], m["confidence"]) for m in data.get("matched", [])])
    assert data["cor_type"] == "regular"
    assert len(data["matched"]) == 2


@pytest.mark.django_db
class TestCorAnalyzeEndpoint:
    def post_cor(
        self, client, content=b"%PDF-fake", name="cor.pdf", ctype="application/pdf"
    ):
        file = SimpleUploadedFile(name, content, content_type=ctype)
        return client.post(reverse("users:cor_analyze"), {"cor_file": file})

    def test_analyze_matches_and_returns_faculty_options(
        self, client, catalog_program, monkeypatch
    ):
        program, year_level, _year = catalog_program
        subject = _make_subject(
            program, year_level, "BSEM 21", "History of Mathematics"
        )
        from apps.users import cor_services as cs

        monkeypatch.setattr(cs, "extract_cor_text", lambda f: "BSEM 21 - History")
        fake_analyzer = type(
            "FakeAnalyzer",
            (),
            {
                "structure_rows": lambda self, text: [
                    {"code": "BSEM 21", "title": "History of Mathematics"}
                ]
            },
        )()
        monkeypatch.setattr(cs, "get_cor_subject_analyzer", lambda: fake_analyzer)
        response = self.post_cor(client)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert len(data["matched"]) == 1
        assert data["matched"][0]["subject_id"] == subject.id
        assert "faculty" in data["matched"][0]

    def test_analyze_rejects_bad_files(self, client):
        file = SimpleUploadedFile("cor.txt", b"zzz", content_type="text/plain")
        response = client.post(reverse("users:cor_analyze"), {"cor_file": file})
        assert response.status_code == 400
        assert response.json()["error"]


@pytest.mark.django_db
class TestCoordinatorRoster:
    def test_add_student_number_registers_pending_entry(self, client):
        coordinator = User.objects.create_user(
            email="coordinator@test.edu",
            password="testpass123",
            role=User.Role.CHAIRPERSON,
        )
        client.force_login(coordinator)
        response = client.post(
            reverse("analytics_chairperson:account_add_student_number"),
            {"student_number": "202400001"},
        )
        assert response.status_code == 302
        entry = PendingStudentRegistration.objects.get(student_number="202400001")
        assert entry.claimed_by_id is None
        assert entry.created_by_id == coordinator.pk

    def test_rejects_numbers_that_are_not_nine_digits(self, client):
        coordinator = User.objects.create_user(
            email="coordinator@test.edu",
            password="testpass123",
            role=User.Role.CHAIRPERSON,
        )
        client.force_login(coordinator)
        client.post(
            reverse("analytics_chairperson:account_add_student_number"),
            {"student_number": "123"},
        )
        assert not PendingStudentRegistration.objects.filter(
            student_number="123"
        ).exists()

    def test_bulk_paste_registers_many_and_skips_dupes(self, client):
        coordinator = User.objects.create_user(
            email="coordinator@test.edu",
            password="testpass123",
            role=User.Role.CHAIRPERSON,
        )
        PendingStudentRegistration.objects.create(student_number="202400002")
        client.force_login(coordinator)
        response = client.post(
            reverse("analytics_chairperson:account_add_student_number"),
            {"student_numbers": "202400001, 202400002\n202400003 bad"},
        )
        assert response.status_code == 302
        assert PendingStudentRegistration.objects.filter(
            student_number="202400001"
        ).exists()
        assert PendingStudentRegistration.objects.filter(
            student_number="202400003"
        ).exists()
        # Dedupe: only one row for the repeated number.
        assert (
            PendingStudentRegistration.objects.filter(
                student_number="202400002"
            ).count()
            == 1
        )

    def test_signup_gate_blocks_unclaimed_number_from_second_student(self, client):
        """A claimed number cannot be reused by another signup."""
        from apps.users.forms import _has_pending_registration

        _bsed_program()
        _term()
        entry = PendingStudentRegistration.objects.create(student_number="202409999")
        first = User.objects.create_user(
            email="first@test.edu",
            password="testpass123",
            role=User.Role.STUDENT,
            student_number="202409999",
        )
        entry.claimed_by = first
        entry.save()
        assert _has_pending_registration("202409999") is False

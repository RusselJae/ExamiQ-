"""Text extraction and chunking from uploaded learning materials."""

from unittest.mock import patch

import pytest

from apps.ai.source_extract import (
    SourceMaterialError,
    chunk_pages,
    extract_pages_from_upload,
)


class _FakeFile:
    def __init__(self, name, raw=b""):
        self.name = name
        self.raw = raw
        self._pos = 0

    def read(self, *_args):
        data = self.raw[self._pos:]
        self._pos = len(self.raw)
        return data

    def seek(self, offset, *_args):
        self._pos = offset


def _fake_ocr(raw, page_number):
    return f"OCR text for page {page_number}: trigonometry sine cosine ratios."


class TestTextAndPlainFiles:
    def test_extracts_txt_file(self):
        upload = _FakeFile("module.txt", b"Linear equations solve for x. Inverse operations.")
        pages = extract_pages_from_upload(upload)
        assert len(pages) == 1
        assert "Linear equations" in pages[0]["text"]
        assert pages[0]["page"] == 1

    def test_empty_file_raises(self):
        upload = _FakeFile("module.txt", b"")
        with pytest.raises(SourceMaterialError):
            extract_pages_from_upload(upload)

    def test_unsupported_file_type_raises(self):
        upload = _FakeFile("module.exe", b"whatever")
        with pytest.raises(SourceMaterialError):
            extract_pages_from_upload(upload)


class TestPdfExtraction:
    @patch("apps.ai.source_extract._build_ocr_function", return_value=None)
    @patch("apps.ai.source_extract._extract_pdf_text_pages", return_value=["", "", ""])
    def test_image_only_pdf_raises_when_ocr_unavailable(self, _text, _ocr):
        upload = _FakeFile("scan.pdf", b"%PDF fake bytes")
        with pytest.raises(SourceMaterialError):
            extract_pages_from_upload(upload)

    @patch(
        "apps.ai.source_extract._build_ocr_function",
        return_value=_fake_ocr,
    )
    @patch("apps.ai.source_extract._extract_pdf_text_pages", return_value=["", "", ""])
    def test_image_pages_are_ocr_fallback(self, _text, _ocr):
        upload = _FakeFile("scan.pdf", b"%PDF fake bytes")
        pages = extract_pages_from_upload(upload)
        assert [p["page"] for p in pages] == [1, 2, 3]
        assert all("OCR text" in p["text"] for p in pages)
        assert "trigonometry" in pages[0]["text"]

    @patch(
        "apps.ai.source_extract._build_ocr_function",
        return_value=_fake_ocr,
    )
    @patch(
        "apps.ai.source_extract._extract_pdf_text_pages",
        return_value=["", "Cosine ratios are fundamental to trigonometry and appear throughout the course.", ""],
    )
    def test_text_layer_pages_are_preferred_over_ocr(self, _text, _ocr):
        upload = _FakeFile("hybrid.pdf", b"%PDF fake bytes")
        pages = extract_pages_from_upload(upload)
        by_page = {p["page"]: p["text"] for p in pages}
        assert "Cosine ratios" in by_page[2]
        assert "OCR text" in by_page[1]
        assert "OCR text" in by_page[3]

    @patch("apps.ai.source_extract._extract_pdf_text_pages", return_value=None)
    def test_raw_scan_fallback_when_no_reader(self, _text):
        upload = _FakeFile("module.pdf", b"%PDF\nParent, Child, (Kid) streaming object names")
        pages = extract_pages_from_upload(upload)
        assert pages
        assert len(pages) == 1


class TestChunking:
    def test_chunks_with_overlap_and_page_ranges(self):
        pages = [{"page": 1, "text": "a" * 2600}]
        chunks = chunk_pages(pages)
        assert len(chunks) >= 3
        assert chunks[0]["page_start"] == 1
        assert chunks[0]["page_end"] == 1
        assert chunks[0]["order"] == 0
        assert chunks[1]["order"] == 1
        assert "a" * 500 in chunks[0]["text"]

"""Extract and chunk plain text from faculty-uploaded learning materials."""

from __future__ import annotations

import io
import logging
import re
import zipfile
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 12000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 120

MIN_PAGE_TEXT_CHARS = 40
OCR_DPI = 200
MAX_OCR_PAGES = 60


class SourceMaterialError(ValueError):
    """Raised when an uploaded file cannot be read as learning material."""


def extract_text_from_upload(uploaded_file) -> str:
    """Return truncated plain text (legacy helper for short prompts)."""
    pages = extract_pages_from_upload(uploaded_file)
    text = re.sub(r"\s+", " ", " ".join(p["text"] for p in pages)).strip()
    if len(text) < 40:
        raise SourceMaterialError(
            "Could not extract enough text from that file. Try a clearer document."
        )
    return text[:MAX_PROMPT_CHARS]


def extract_pages_from_upload(uploaded_file) -> list[dict]:
    """Return list of {page, text} for the full document."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    raw = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
    if not raw:
        raise SourceMaterialError("Uploaded file is empty.")

    if name.endswith((".txt", ".md", ".csv")):
        text = _decode_bytes(raw)
        pages = [{"page": 1, "text": text}]
    elif name.endswith(".docx"):
        text = _extract_docx(raw)
        pages = [{"page": 1, "text": text}]
    elif name.endswith(".pdf"):
        pages = _extract_pdf_pages(raw)
    else:
        raise SourceMaterialError(
            "Unsupported file type. Upload a TXT, MD, DOCX, or PDF file."
        )

    cleaned = []
    for item in pages:
        text = re.sub(r"\s+", " ", (item.get("text") or "")).strip()
        if text:
            cleaned.append({"page": int(item["page"]), "text": text})
    if not cleaned or sum(len(p["text"]) for p in cleaned) < 40:
        raise SourceMaterialError(
            "Could not extract enough text from that file. Try a clearer document."
        )
    return cleaned


def chunk_pages(pages: list[dict], *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Split page texts into overlapping chunks with page ranges."""
    chunks: list[dict] = []
    order = 0
    for page in pages:
        page_no = page["page"]
        text = page["text"]
        if len(text) <= chunk_size:
            chunks.append(
                {
                    "order": order,
                    "page_start": page_no,
                    "page_end": page_no,
                    "text": text,
                }
            )
            order += 1
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    {
                        "order": order,
                        "page_start": page_no,
                        "page_end": page_no,
                        "text": piece,
                    }
                )
                order += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise SourceMaterialError("Invalid DOCX file.") from exc
    root = ElementTree.fromstring(xml)
    texts = [
        node.text
        for node in root.iter()
        if node.tag.endswith("}t") and node.text
    ]
    return " ".join(texts)


def _extract_pdf_pages(raw: bytes) -> list[dict]:
    """Return list of {page, text} for the full PDF document.

    Prefers the embedded text layer (pypdf, falling back to PyMuPDF). Pages
    that yield little or no text are OCR'd when PyMuPDF + pytesseract + the
    Tesseract binary are available. Every failure mode degrades gracefully:
    image-only pages simply keep their (possibly empty) text.
    """
    page_texts = _extract_pdf_text_pages(raw)
    if page_texts is None:
        chunks = re.findall(rb"[\x20-\x7E]{6,}", raw)
        text = " ".join(c.decode("latin-1", errors="ignore") for c in chunks)
        return [{"page": 1, "text": text}]

    ocr_page = _build_ocr_function()
    ocr_used = 0
    pages = []
    for index, text in enumerate(page_texts, start=1):
        text = (text or "").strip()
        if (
            ocr_page is not None
            and len(text) < MIN_PAGE_TEXT_CHARS
            and ocr_used < MAX_OCR_PAGES
        ):
            try:
                ocr_text = ocr_page(raw, index)
                if ocr_text and len(ocr_text) >= len(text):
                    text = ocr_text
                ocr_used += 1
            except Exception as exc:
                logger.warning("OCR failed for PDF page %s: %s", index, exc)
        pages.append({"page": index, "text": text})
    return pages


def _extract_pdf_text_pages(raw: bytes) -> list[str] | None:
    """Extract the embedded text layer page-by-page; None when no reader works."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return [page.extract_text() or "" for page in reader.pages]
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("pypdf text extraction failed (%s); trying PyMuPDF.", exc)

    try:
        import fitz

        doc = fitz.open(stream=raw, filetype="pdf")
        try:
            return [page.get_text() or "" for page in doc]
        finally:
            doc.close()
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("PyMuPDF text extraction failed (%s); using raw scan.", exc)
        return None


def _build_ocr_function():
    """Return an (raw_bytes, page_number) -> text callable, or None when
    the OCR stack (PyMuPDF + pytesseract + PIL) is not available."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning(
            "OCR stack unavailable (need PyMuPDF + pytesseract); "
            "image-only PDF pages will not be transcribed."
        )
        return None

    def _ocr_page(raw: bytes, page_number: int) -> str:
        doc = fitz.open(stream=raw, filetype="pdf")
        try:
            if page_number > len(doc):
                return ""
            pix = doc[page_number - 1].get_pixmap(dpi=OCR_DPI)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            return (pytesseract.image_to_string(image) or "").strip()
        finally:
            doc.close()

    return _ocr_page

"""Extract and chunk plain text from faculty-uploaded learning materials."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree


MAX_PROMPT_CHARS = 12000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 120


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
    try:
        from pypdf import PdfReader
    except ImportError:
        chunks = re.findall(rb"[\x20-\x7E]{6,}", raw)
        text = " ".join(c.decode("latin-1", errors="ignore") for c in chunks)
        return [{"page": 1, "text": text}]

    reader = PdfReader(io.BytesIO(raw))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append({"page": index, "text": page.extract_text() or ""})
    return pages

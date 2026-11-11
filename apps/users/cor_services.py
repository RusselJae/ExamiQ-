"""COR (Certificate of Registration) upload analysis for irregular students.

Pipeline: deterministic text extraction (PDF text layer, OCR fallback) →
LLM structuring (never inventing codes) → fuzzy match against the program's
subject catalog → review screen. Nothing saves without the student
confirming, and matching never creates enrollments on its own.
"""

from __future__ import annotations

import logging
import re

from apps.ai.factory import get_cor_subject_analyzer
from apps.users.models import User

logger = logging.getLogger(__name__)

MAX_COR_CHARS = 12000
ALLOWED_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp")

#: Long schedule/section codes printed beside the real curriculum code
#: (e.g. ``BSEM10019``). These never match the subject catalog.
SCHEDULE_CODE_RE = re.compile(r"^BSEM1\d{4,}$")


class CorAnalysisError(ValueError):
    """Raised when the uploaded COR cannot be read at all."""


def normalize_code(code: str) -> str:
    """Uppercase, strip punctuation, collapse whitespace: ``GE 3`` → ``GE3``."""
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def is_schedule_code(code: str) -> bool:
    """True for COR schedule codes like ``BSEM10018`` (not course codes)."""
    return bool(SCHEDULE_CODE_RE.fullmatch(normalize_code(code)))


def classify_cor_type(text: str) -> str:
    """Classify a COR by its printed student type.

    Returns ``"regular"`` when the word "regular" appears, ``"irregular"``
    when only that word appears, else ``"unknown"``. Used to stop irregular
    students from slipping through the regular signup path.
    """
    haystack = text or ""
    has_regular = re.search(r"\bregular\b", haystack, re.IGNORECASE) is not None
    has_irregular = re.search(r"\birregular\b", haystack, re.IGNORECASE) is not None
    if has_regular:
        return "regular"
    if has_irregular:
        return "irregular"
    return "unknown"


def suggest_year_level(matched: list[dict]) -> dict | None:
    """Most common year level across matched subjects (mode, ties → lowest).

    Returns ``{"id": ..., "name": ...}`` or ``None`` when nothing matched.
    """
    if not matched:
        return None
    counts: dict[int, int] = {}
    for entry in matched:
        year_id = entry.get("year_level_id")
        if year_id:
            counts[year_id] = counts.get(year_id, 0) + 1
    if not counts:
        return None
    from apps.questions.models import YearLevel

    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    year = YearLevel.objects.filter(pk=best).first()
    if year is None:
        return None
    return {"id": year.pk, "name": year.name}


def _ocr_image(raw: bytes, mime_type: str = "") -> str:
    """Read a COR photo with Tesseract, then fall back to the vision model.

    Tesseract is optional; many hosted environments do not ship the binary.
    The AI fallback keeps photo uploads usable without a system package.
    """
    text = _tesseract_image_text(raw)
    if len(text) >= 40:
        return text

    from apps.ai.vision import extract_text_from_image

    vision_text = extract_text_from_image(raw, mime_type or "image/jpeg")
    if vision_text:
        return vision_text
    return text


def _tesseract_image_text(raw: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - optional dependency
        logger.info("OCR unavailable for COR image: %s", exc)
        return ""
    try:
        image = Image.open(_bytes_io(raw))
        image = ImageOps.exif_transpose(image)
        gray = image.convert("L")
        # Small phone crops OCR poorly; upscale and normalize contrast.
        if gray.width < 1600:
            ratio = 1600 / max(gray.width, 1)
            gray = gray.resize(
                (int(gray.width * ratio), int(gray.height * ratio)),
                Image.LANCZOS,
            )
        gray = ImageOps.autocontrast(gray)
        best = ""
        # psm 6 treats the page as a uniform block (best for tables); psm 3
        # is a useful fallback for sparse layouts.
        for psm in (6, 3):
            try:
                candidate = (
                    pytesseract.image_to_string(gray, config=f"--psm {psm}") or ""
                ).strip()
            except Exception as exc:  # noqa: BLE001 - try the next mode
                logger.info("Tesseract psm %s failed: %s", psm, exc)
                continue
            if len(candidate) > len(best):
                best = candidate
        return best
    except Exception as exc:  # noqa: BLE001 - OCR failure must not 500
        logger.warning("COR image OCR failed: %s", exc)
        return ""


def _bytes_io(raw: bytes):
    import io

    return io.BytesIO(raw)


def extract_cor_text(uploaded_file) -> str:
    """Deterministic text extraction for an uploaded COR (PDF or image)."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    raw = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except Exception:  # noqa: BLE001
            pass
    if not raw:
        raise CorAnalysisError("That file is empty.")

    if name.endswith(".pdf"):
        from apps.ai.source_extract import extract_pages_from_upload

        class _Wrapped:
            """Extract expects an UploadedFile-ish object carrying the bytes."""

            def __init__(self, data: bytes, filename: str):
                self._data = data
                self.name = filename

            def read(self):
                return self._data

            def seek(self, *_args):
                return None

            def tell(self):
                return len(self._data)

        try:
            pages = extract_pages_from_upload(_Wrapped(raw, name))
        except Exception as exc:  # noqa: BLE001 - source errors degrade to OCR
            logger.warning("COR PDF extraction failed: %s", exc)
            pages = []
        text = " ".join(p["text"] for p in pages).strip()
        if len(text) < 40:
            text = _ocr_image(raw, "application/pdf")
        if not text:
            raise CorAnalysisError(
                "Could not read that COR. Try a clearer photo or a text PDF."
            )
        return text[:MAX_COR_CHARS]

    if name.endswith(ALLOWED_EXTENSIONS[1:]):
        mime_type = getattr(uploaded_file, "content_type", "") or ""
        text = _ocr_image(raw, mime_type)
        if not text:
            raise CorAnalysisError(
                "Could not read that photo. Retake it with better light and no glare."
            )
        return text[:MAX_COR_CHARS]

    raise CorAnalysisError("Upload the COR as a PDF, PNG, or JPG.")


def _titles_match(catalog_title: str, extracted_title: str) -> float:
    """Token-overlap coefficient between two subject titles (0..1)."""
    stop = {"the", "and", "of", "in", "to", "for", "a", "an", "i", "ii", "iii"}
    a = {
        w
        for w in re.findall(r"[a-z0-9]+", (catalog_title or "").lower())
        if w not in stop
    }
    b = {
        w
        for w in re.findall(r"[a-z0-9]+", (extracted_title or "").lower())
        if w not in stop
    }
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def match_cor_rows(rows: list[dict[str, str]]) -> dict:
    """Match extracted COR rows to the program's subject catalog.

    Returns ``{"matched": [...], "unmatched": [...]}`` where each matched
    entry carries the ``Subject`` and confidence band so the signup review
    screen can flag low-confidence picks.
    """
    from apps.questions.models import Subject
    from apps.users.models import Program

    program = Program.for_home_degree(User.HomeDegreeProgram.BSED_MATH)
    catalog = list(
        Subject.objects.filter(program=program)
        .select_related("year_level")
        .only("id", "code", "name", "year_level_id", "year_level__name")
    )
    by_normalized: dict[str, list] = {}
    for subject in catalog:
        by_normalized.setdefault(normalize_code(subject.code), []).append(subject)

    matched: list[dict] = []
    unmatched: list[dict] = []
    used_subject_ids: set[int] = set()
    for row in rows:
        code = (row.get("code") or "").strip().upper()
        title = (row.get("title") or "").strip()
        if not code:
            continue
        schedule_code = is_schedule_code(code)
        norm = "" if schedule_code else normalize_code(code)
        subject = None
        confidence = "low"
        if norm and by_normalized.get(norm):
            subject = by_normalized[norm][0]
            confidence = "high"
        if subject is None and norm:
            for catalog_norm, subjects in by_normalized.items():
                if (
                    norm
                    and catalog_norm.startswith(norm)
                    or norm.startswith(catalog_norm)
                ):
                    subject = subjects[0]
                    confidence = "medium"
                    break
        if subject is None and title:
            best, best_score = None, 0.0
            for candidate in catalog:
                score = _titles_match(candidate.name, title)
                if score > best_score:
                    best, best_score = candidate, score
            if best_score >= 0.7:
                subject = best
                confidence = "medium" if best_score >= 0.9 else "low"
        if subject is None or subject.id in used_subject_ids:
            unmatched.append({"code": code, "title": title})
            continue
        used_subject_ids.add(subject.id)
        matched.append(
            {
                "subject_id": subject.id,
                "code": subject.code,
                "name": subject.name,
                "year_level_id": subject.year_level_id,
                "year_level_name": subject.year_level.name,
                "confidence": confidence,
                "printed_code": code,
                "printed_title": title,
            }
        )
    return {"matched": matched, "unmatched": unmatched}


def analyze_cor_upload(uploaded_file) -> dict:
    """Full non-persisting analyze pass: read → structure → match."""
    text = extract_cor_text(uploaded_file)
    rows = get_cor_subject_analyzer().structure_rows(text)
    if not rows:
        return {
            "ok": True,
            "rows": [],
            "matched": [],
            "unmatched": [],
            "text_chars": len(text),
            "cor_type": classify_cor_type(text),
            "suggested_year_level": None,
        }
    result = match_cor_rows(rows)
    result["ok"] = True
    result["rows"] = [
        {"code": r.get("code", ""), "title": r.get("title", "")} for r in rows
    ]
    result["text_chars"] = len(text)
    result["cor_type"] = classify_cor_type(text)
    result["suggested_year_level"] = suggest_year_level(result["matched"])
    return result


COR_SESSION_KEY = "cor_verified"


def store_cor_verification(request, uploaded, result: dict) -> None:
    """Cache the analyze-time conclusions server-side for signup validation.

    Hidden fields are forgeable; the session bundle is not. Keyed off the
    analyzed file's name + size so a swapped file fails closed.
    """
    request.session[COR_SESSION_KEY] = {
        "name": getattr(uploaded, "name", ""),
        "size": getattr(uploaded, "size", 0),
        "cor_type": result.get("cor_type", "unknown"),
        "year_level_id": (result.get("suggested_year_level") or {}).get("id"),
        "subject_ids": [m["subject_id"] for m in result.get("matched", [])],
        "rows": result.get("rows", []),
    }


def verify_cor_submission(
    request, uploaded, *, is_irregular: bool, year_level_id, course_ids
) -> str | None:
    """Validate the signup POST against the analyzed COR. Returns error or None."""
    bundle = request.session.get(COR_SESSION_KEY)
    if not isinstance(bundle, dict):
        return "Please analyze your COR first, then submit."
    if bundle.get("name") != getattr(uploaded, "name", "") or bundle.get(
        "size"
    ) != getattr(uploaded, "size", 0):
        return "That COR file changed since analysis. Analyze it again, then submit."
    if not bundle.get("subject_ids"):
        return "No courses were detected on that COR. Try a clearer photo or PDF."
    if not is_irregular and bundle.get("cor_type") != "regular":
        return (
            "Your COR does not show regular status. If you are an irregular "
            "student, sign up as irregular instead."
        )
    if is_irregular and bundle.get("cor_type") == "regular":
        return (
            "Your COR shows a regular status. If you are a regular student, "
            "switch to regular and pick your year level and section instead."
        )
    if not is_irregular:
        if year_level_id in (None, ""):
            return "No year level was detected on that COR. Analyze it again."
        try:
            wanted = int(year_level_id)
        except (TypeError, ValueError):
            return "The detected year level is invalid. Analyze your COR again."
        if bundle.get("year_level_id") != wanted:
            return "That year level does not match your COR. Analyze it again."
    verified_subjects = set(bundle.get("subject_ids") or [])
    for course_id in course_ids or []:
        try:
            cid = int(course_id)
        except (TypeError, ValueError):
            return "A selected course is invalid. Analyze your COR again."
        if cid not in verified_subjects:
            return "A selected course is not on your COR. Analyze it again."
    if is_irregular and not (course_ids or []):
        return "Select at least one course."
    return None

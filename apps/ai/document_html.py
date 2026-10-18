"""Convert uploaded learning material between DOCX/Markdown, HTML, and text.

The material editor is an HTML surface, so every supported upload is translated
into a small, sanitized subset of HTML (``<h1>``–``<h3>``, ``<p>``, ``<ul>``,
``<ol>``, ``<strong>``, ``<em>``, ``<img>``). Plain text is kept in parallel for
AI retrieval, which works off plain text rather than markup.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import re
import zipfile

import bleach
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Narrow whitelist: this HTML is rendered in the browser and re-exported to
# DOCX, so anything scriptable, styleable, or frameable stays out.
ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "ul", "ol", "li",
    "strong", "b", "em", "i", "u", "s",
    "img", "a",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "p": ["align"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]

MAMMOTH_STYLE_MAP = """
p[style-name='Title'] => h1:fresh
p[style-name='Subtitle'] => h2:fresh
p[style-name='Heading 1'] => h1:fresh
p[style-name='Heading 2'] => h2:fresh
p[style-name='Heading 3'] => h3:fresh
p[style-name='Heading 4'] => h4:fresh
p[style-name='Heading 5'] => h5:fresh
p[style-name='Heading 6'] => h6:fresh
p[style-name='Quote'] => blockquote:fresh
p[style-name='Intense Quote'] => blockquote:fresh
p[style-name='List Paragraph'] => p:fresh
b => strong
i => em
"""

MAX_IMAGE_BYTES = 4 * 1024 * 1024
_BLOCK_TAGS = (
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote", "pre",
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")


class DocumentConversionError(ValueError):
    """Raised when a file cannot be translated into editor HTML."""


# --------------------------------------------------------------------------- #
# Sanitising
# --------------------------------------------------------------------------- #
def sanitize_html(html: str) -> str:
    """Strip everything outside the editor's whitelist.

    ``script``/``style`` bodies are removed rather than unwrapped: bleach's
    ``strip=True`` deletes the tags but keeps the text, which would otherwise
    dump JavaScript source into the document as visible copy.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "object", "embed"]):
        tag.decompose()
    return bleach.clean(
        str(soup),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def _strip_data_uri_images(html: str) -> str:
    """Drop <img> tags whose src is a data: URI (too heavy to persist)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("img"):
        src = (tag.get("src") or "").strip()
        if src.lower().startswith("data:"):
            tag.decompose()
    return str(soup)


def _decode_data_uri(src: str) -> bytes | None:
    if "," not in src:
        return None
    header, payload = src.split(",", 1)
    if "base64" not in header.lower():
        return None
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        return None
    return raw if len(raw) <= MAX_IMAGE_BYTES else None


# --------------------------------------------------------------------------- #
# HTML -> plain text (for AI retrieval)
# --------------------------------------------------------------------------- #
def html_to_text(html: str) -> str:
    """Flatten editor HTML into the plain text AI retrieval expects."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Only outermost blocks, otherwise a table row and its cells are all
    # emitted and the same words repeat two or three times.
    blocks: list[str] = []
    for node in soup.find_all(_BLOCK_TAGS):
        if node.find_parent(_BLOCK_TAGS) is not None:
            continue
        # Space between inline runs: without it "The <strong>sine</strong>
        # ratio" collapses to "Thesineratio".
        text = re.sub(r"[ \t]*\n[ \t]*", " ", node.get_text(" "))
        text = re.sub(r"\s{2,}", " ", text).strip()
        # Inline-tag boundaries leave "italic ." — tidy before punctuation.
        text = re.sub(r"\s+([.,;:!?])", r"\1", text)
        if not text:
            continue
        prefix = ""
        if node.name.startswith("h") and len(node.name) == 2 and node.name[1].isdigit():
            prefix = "#" * int(node.name[1]) + " "
        blocks.append(f"{prefix}{text}")

    if blocks:
        return "\n\n".join(blocks)

    # Fallback for content with no block elements at all.
    return " ".join(soup.stripped_strings).strip()


def text_to_html(text: str) -> str:
    """Translate plain text / Markdown into editor HTML paragraphs."""
    if not text or not text.strip():
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag = "ul"

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            chunks.append("<p>" + _inline_markup(" ".join(paragraph).strip()) + "</p>")
            paragraph = []

    def flush_list():
        nonlocal list_items
        if list_items:
            chunks.append(
                f"<{list_tag}>"
                + "".join(f"<li>{_inline_markup(item)}</li>" for item in list_items)
                + f"</{list_tag}>"
            )
            list_items = []

    def flush_all():
        flush_paragraph()
        flush_list()

    for raw_line in lines:
        line = raw_line.rstrip()

        if not line.strip():
            flush_all()
            continue

        heading = _HEADING_RE.match(line.strip())
        if heading:
            flush_all()
            level = len(heading.group(1))
            chunks.append(
                f"<h{level}>{_inline_markup(heading.group(2).strip())}</h{level}>"
            )
            continue

        bullet = _BULLET_RE.match(line)
        ordered = _ORDERED_RE.match(line)
        if bullet or ordered:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_items and wanted != list_tag:
                flush_list()
            list_tag = wanted
            list_items.append((bullet or ordered).group(1).strip())
            continue

        flush_list()
        paragraph.append(line.strip())

    flush_all()
    return sanitize_html("\n".join(chunks))


def _inline_markup(text: str) -> str:
    """Escape, then re-apply the small Markdown inline subset we support."""
    from html import escape

    out = escape(text or "", quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(
        _IMAGE_MD_RE,
        lambda m: f'<img alt="{m.group(1)}" src="{m.group(2)}">',
        out,
    )
    return out


# --------------------------------------------------------------------------- #
# Upload -> HTML
# --------------------------------------------------------------------------- #
def html_from_docx(raw: bytes) -> str:
    """Convert a .docx to sanitized HTML, preserving headings/lists/bold/images."""
    try:
        import mammoth
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise DocumentConversionError("DOCX support is unavailable.") from exc

    with io.BytesIO(raw) as handle:
        result = mammoth.convert_to_html(
            handle,
            style_map=MAMMOTH_STYLE_MAP,
            convert_image=mammoth.images.data_uri,
        )
    return sanitize_html(result.value)


def html_from_upload(name: str, raw: bytes, *, extracted_text: str = "") -> str:
    """Translate an uploaded file into editor HTML.

    ``extracted_text`` is the already-extracted plain text used as the fallback
    for formats with no markup (PDF and anything else).
    """
    lowered = (name or "").lower()
    if lowered.endswith(".docx"):
        try:
            return html_from_docx(raw)
        except DocumentConversionError:
            raise
        except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
            # Malformed OOXML: fall back to the extracted plain text so the
            # document is still editable rather than opaque.
            logger.warning("DOCX conversion failed for %s: %s", name, exc)
            return text_to_html(extracted_text)
    return text_to_html(extracted_text)


# --------------------------------------------------------------------------- #
# HTML -> DOCX
# --------------------------------------------------------------------------- #
_DOCX_HEADING = {"h1": "Heading 1", "h2": "Heading 2", "h3": "Heading 3",
                 "h4": "Heading 4", "h5": "Heading 5", "h6": "Heading 6"}
_DOCX_LIST = {"ul": "List Bullet", "ol": "List Number"}
_DOCX_ALIGN = {"left": "LEFT", "center": "CENTER", "right": "RIGHT", "justify": "JUSTIFY"}


def html_to_docx_bytes(html: str, *, title: str = "") -> bytes:
    """Render editor HTML back into a .docx so downloads round-trip."""
    try:
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches
        from PIL import UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise DocumentConversionError("DOCX export is unavailable.") from exc

    document = docx.Document()
    if title:
        try:
            document.core_properties.title = title
        except (AttributeError, ValueError):
            pass

    aligns = {
        "LEFT": WD_ALIGN_PARAGRAPH.LEFT,
        "CENTER": WD_ALIGN_PARAGRAPH.CENTER,
        "RIGHT": WD_ALIGN_PARAGRAPH.RIGHT,
        "JUSTIFY": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    soup = BeautifulSoup(html or "", "html.parser")

    def add_runs(paragraph, node, *, bold=False, italic=False):
        for child in node.children:
            if getattr(child, "name", None) is None:
                if str(child).strip():
                    paragraph.add_run(str(child)).bold = bold or None
                continue
            name = child.name
            if name in ("strong", "b"):
                add_runs(paragraph, child, bold=True, italic=italic)
            elif name in ("em", "i"):
                add_runs(paragraph, child, bold=bold, italic=True)
            elif name == "br":
                paragraph.add_run().add_break()
            elif name == "img":
                _append_image(paragraph, child)
            else:
                add_runs(paragraph, child, bold=bold, italic=italic)

    def add_paragraph(node, style=None, *, list_style=None):
        if list_style:
            try:
                paragraph = document.add_paragraph(style=list_style)
            except KeyError:
                paragraph = document.add_paragraph()
        else:
            paragraph = document.add_paragraph(style=style) if style else document.add_paragraph()
        align = aligns.get((node.get("align") or "").upper())
        if align is not None:
            paragraph.alignment = align
        add_runs(paragraph, node)
        return paragraph

    def _append_image(paragraph, node):
        src = (node.get("src") or "").strip()
        raw = _decode_data_uri(src) if src.lower().startswith("data:") else None
        if not raw:
            return
        try:
            stream = io.BytesIO(raw)
            width = node.get("width")
            run = paragraph.add_run()
            if width and str(width).isdigit():
                run.add_picture(stream, width=Inches(min(int(width), 4096) / 96))
            else:
                run.add_picture(stream)
        except (ValueError, TypeError, OSError, UnidentifiedImageError) as exc:
            # A corrupt or unsupported image must not abort the whole export.
            logger.warning("Could not embed image from editor HTML: %s", exc)

    def walk(node):
        for child in node.children:
            name = getattr(child, "name", None)
            if name is None:
                continue
            if name in _DOCX_HEADING:
                add_paragraph(child, style=_DOCX_HEADING[name])
            elif name == "p":
                add_paragraph(child)
            elif name in ("ul", "ol"):
                for item in child.find_all("li", recursive=False):
                    add_paragraph(item, list_style=_DOCX_LIST[name])
            elif name == "img":
                paragraph = document.add_paragraph()
                _append_image(paragraph, child)
            elif name == "blockquote":
                for para in child.find_all("p", recursive=False) or [child]:
                    add_paragraph(para, style="Intense Quote")
            elif name == "pre":
                add_paragraph(child, style="No Spacing")
            elif name == "hr":
                document.add_paragraph("―" * 24)
            elif name in ("table", "thead", "tbody"):
                walk_table(child)
            else:
                walk(child)

    def walk_table(node):
        rows = node.find_all("tr")
        if not rows:
            return
        table = document.add_table(rows=len(rows), cols=len(rows[0].find_all(["td", "th"])))
        try:
            table.style = "Table Grid"
        except KeyError:
            pass
        for r_index, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            for c_index, cell in enumerate(cells):
                if c_index >= len(table.columns):
                    break
                target = table.cell(r_index, c_index)
                target.text = ""
                add_runs(target.paragraphs[0], cell)

    walk(soup)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


__all__ = [
    "ALLOWED_TAGS",
    "DocumentConversionError",
    "html_from_docx",
    "html_from_upload",
    "html_to_docx_bytes",
    "html_to_text",
    "sanitize_html",
    "text_to_html",
]
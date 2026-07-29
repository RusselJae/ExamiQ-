#!/usr/bin/env python3
"""Generate BSEd Mathematics student survey and chairperson interview PDFs."""

from pathlib import Path
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bsed_research_instruments_data import (  # noqa: E402
    CHAIR_CLOSING_QUESTIONS,
    CHAIR_EDGE_MAPPING,
    CHAIR_INTERVIEW_BLOCKS,
    CHAIR_INTERVIEW_META,
    STUDENT_EDGE_MAPPING,
    STUDENT_POST_SECTIONS,
    STUDENT_PRE_SECTIONS,
    STUDENT_SURVEY_META,
)

STUDENT_OUTPUT = ROOT / "docs" / "thesis" / "bsed-student-survey.pdf"
CHAIR_OUTPUT = ROOT / "docs" / "thesis" / "bsed-chairperson-interview-guide.pdf"

styles = getSampleStyleSheet()
TITLE = ParagraphStyle(
    "DocTitle",
    parent=styles["Heading1"],
    fontSize=15,
    spaceAfter=8,
    alignment=TA_CENTER,
    textColor=colors.HexColor("#0f172a"),
)
SUBTITLE = ParagraphStyle(
    "DocSubtitle",
    parent=styles["Normal"],
    fontSize=9,
    spaceAfter=14,
    alignment=TA_CENTER,
    textColor=colors.HexColor("#64748b"),
)
H1 = ParagraphStyle(
    "DocH1",
    parent=styles["Heading1"],
    fontSize=12,
    spaceBefore=14,
    spaceAfter=8,
    textColor=colors.HexColor("#0f172a"),
)
H2 = ParagraphStyle(
    "DocH2",
    parent=styles["Heading2"],
    fontSize=10.5,
    spaceBefore=10,
    spaceAfter=6,
    textColor=colors.HexColor("#1e3a5f"),
)
BODY = ParagraphStyle(
    "DocBody",
    parent=styles["Normal"],
    fontSize=9.5,
    leading=13,
    alignment=TA_JUSTIFY,
    spaceAfter=8,
)
ITEM = ParagraphStyle(
    "DocItem",
    parent=styles["Normal"],
    fontSize=9.5,
    leading=13,
    leftIndent=10,
    spaceAfter=6,
    alignment=TA_LEFT,
)
NOTE = ParagraphStyle(
    "DocNote",
    parent=styles["Normal"],
    fontSize=8.5,
    leading=12,
    leftIndent=10,
    textColor=colors.HexColor("#475569"),
    spaceAfter=6,
)
FOOTNOTE = ParagraphStyle(
    "DocFoot",
    parent=styles["Normal"],
    fontSize=8,
    leading=11,
    textColor=colors.HexColor("#64748b"),
    spaceBefore=16,
)
CELL = ParagraphStyle("DocCell", parent=styles["Normal"], fontSize=8.5, leading=11, alignment=TA_LEFT)


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def p(text: str, style=BODY) -> Paragraph:
    return Paragraph(esc(text), style)


def make_table(headers: list[str], rows: list[list[str]], col_widths: list[float]) -> Table:
    data = [[Paragraph(esc(h), CELL) for h in headers]]
    for row in rows:
        data.append([Paragraph(esc(c), CELL) for c in row])
    table = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a5632")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _type_label(qtype: str) -> str:
    return {
        "Likert": "Likert 1–5",
        "MC": "Multiple choice",
        "Open": "Open-ended",
        "Rank": "Ranking",
    }.get(qtype, qtype)


def _render_survey_sections(story: list, sections: list, start_number: int) -> int:
    number = start_number
    for section_title, items in sections:
        story.append(p(section_title, H1))
        for qtype, prompt, note in items:
            story.append(p(f"{number}. [{_type_label(qtype)}] {prompt}", ITEM))
            if note:
                story.append(p(f"Note: {note}", NOTE))
            number += 1
        story.append(Spacer(1, 6))
    return number


def build_student_survey() -> None:
    story: list = []
    story.append(Spacer(1, 2 * cm))
    story.append(p(STUDENT_SURVEY_META["title"], TITLE))
    story.append(p(STUDENT_SURVEY_META["subtitle"], SUBTITLE))
    story.append(p(STUDENT_SURVEY_META["purpose"], BODY))
    story.append(p(STUDENT_SURVEY_META["likert_note"], NOTE))
    story.append(PageBreak())

    story.append(p("Part A — Pre-Study Survey", H1))
    story.append(
        p(
            "Administer before the student's first ExamiQ review session. "
            "Items marked 'Core thesis item' align with the pilot protocol for pre/post comparison.",
            BODY,
        )
    )
    next_num = _render_survey_sections(story, STUDENT_PRE_SECTIONS, start_number=1)

    story.append(PageBreak())
    story.append(p("Part B — Post-Study Survey", H1))
    story.append(
        p(
            "Administer after 2–4 weeks of ExamiQ use. Students may complete this from Profile "
            "without a session gate. Retain core thesis items for statistical comparison.",
            BODY,
        )
    )
    _render_survey_sections(story, STUDENT_POST_SECTIONS, start_number=next_num)

    story.append(PageBreak())
    story.append(p("Appendix — Mapping Responses to System Improvements", H1))
    story.append(
        p(
            "Use this table when analyzing open-ended answers and Likert patterns. "
            "It links common BSEd Math needs to ExamiQ capabilities that provide thesis edge.",
            BODY,
        )
    )
    story.append(
        make_table(
            ["If students report…", "ExamiQ direction / edge"],
            STUDENT_EDGE_MAPPING,
            [7.5 * cm, 9.5 * cm],
        )
    )
    story.append(p("ExamiQ+ · BSEd Mathematics pilot · Student survey instrument", FOOTNOTE))

    STUDENT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(STUDENT_OUTPUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=STUDENT_SURVEY_META["title"],
        author="ExamiQ+",
    )
    doc.build(story)
    print(f"Wrote {STUDENT_OUTPUT}")


def build_chair_interview() -> None:
    story: list = []
    story.append(Spacer(1, 2 * cm))
    story.append(p(CHAIR_INTERVIEW_META["title"], TITLE))
    story.append(p(CHAIR_INTERVIEW_META["subtitle"], SUBTITLE))
    story.append(p(CHAIR_INTERVIEW_META["purpose"], BODY))
    story.append(p(f"Format: {CHAIR_INTERVIEW_META['format']}", NOTE))
    story.append(PageBreak())

    question_number = 1
    for block_title, questions in CHAIR_INTERVIEW_BLOCKS:
        story.append(p(block_title, H1))
        for question, probe in questions:
            story.append(p(f"{question_number}. {question}", ITEM))
            story.append(p(f"Probe: {probe}", NOTE))
            question_number += 1
        story.append(Spacer(1, 6))

    story.append(p("Closing Questions", H1))
    for question, probe in CHAIR_CLOSING_QUESTIONS:
        story.append(p(f"{question_number}. {question}", ITEM))
        story.append(p(f"Probe: {probe}", NOTE))
        question_number += 1

    story.append(PageBreak())
    story.append(p("Appendix — Institutional Needs to ExamiQ Edge", H1))
    story.append(
        p(
            "Summarize chairperson responses using this mapping when drafting thesis "
            "recommendations and defense talking points.",
            BODY,
        )
    )
    story.append(
        make_table(
            ["Department need", "ExamiQ capability"],
            CHAIR_EDGE_MAPPING,
            [7.5 * cm, 9.5 * cm],
        )
    )
    story.append(p("ExamiQ+ · BSEd Mathematics pilot · Chairperson interview guide", FOOTNOTE))

    CHAIR_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(CHAIR_OUTPUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=CHAIR_INTERVIEW_META["title"],
        author="ExamiQ+",
    )
    doc.build(story)
    print(f"Wrote {CHAIR_OUTPUT}")


def build() -> None:
    build_student_survey()
    build_chair_interview()


if __name__ == "__main__":
    build()

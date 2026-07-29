#!/usr/bin/env python3
"""Generate docs/thesis/own-ai-model-feasibility.pdf from panel guidance notes."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "thesis" / "own-ai-model-feasibility.pdf"

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
    spaceAfter=16,
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
BODY = ParagraphStyle(
    "DocBody",
    parent=styles["Normal"],
    fontSize=9.5,
    leading=13,
    alignment=TA_JUSTIFY,
    spaceAfter=8,
)
BULLET = ParagraphStyle(
    "DocBullet",
    parent=styles["Normal"],
    fontSize=9.5,
    leading=13,
    leftIndent=14,
    spaceAfter=4,
    alignment=TA_LEFT,
)
QUOTE = ParagraphStyle(
    "DocQuote",
    parent=styles["Normal"],
    fontSize=9.5,
    leading=13,
    leftIndent=12,
    rightIndent=12,
    spaceBefore=6,
    spaceAfter=10,
    textColor=colors.HexColor("#1e293b"),
    borderPadding=6,
)
CELL = ParagraphStyle(
    "DocCell",
    parent=styles["Normal"],
    fontSize=8.5,
    leading=11,
    alignment=TA_LEFT,
)
FOOTNOTE = ParagraphStyle(
    "DocFoot",
    parent=styles["Normal"],
    fontSize=8,
    leading=11,
    textColor=colors.HexColor("#64748b"),
    spaceBefore=16,
)


def p(text: str, style=BODY):
    return Paragraph(text.replace("\n", "<br/>"), style)


def table(headers: list[str], rows: list[list[str]], col_widths: list[float]):
    data = [[Paragraph(h, CELL) for h in headers]]
    for row in rows:
        data.append([Paragraph(c, CELL) for c in row])
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
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
    return t


def build():
    story = []
    story.append(p("Is It Possible to Make Our Own AI/NLP Model?", TITLE))
    story.append(
        p(
            "ExamiQ+ thesis guidance — feasibility of custom models vs hosted LLM inference",
            SUBTITLE,
        )
    )

    story.append(
        p(
            "<b>Yes in a limited sense — no as in “train our own GPT from scratch.”</b>",
            BODY,
        )
    )

    story.append(p("What’s <i>not</i> realistic for your thesis", H1))
    story.append(
        table(
            ["Idea", "Why not"],
            [
                [
                    "Train GPT/BERT from scratch",
                    "Needs huge data, GPUs, months, ML research skillset",
                ],
                [
                    "Fine-tune a big model on all student data",
                    "Privacy/ethics, small N, weak results, hard to defend",
                ],
                [
                    "Match Ollama/Gemini quality alone",
                    "Commercial models win; you’d underperform and spend the whole thesis on ML",
                ],
            ],
            [6.5 * cm, 10.5 * cm],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        p(
            "That’s why ExamiQ correctly uses a hosted LLM for generation and tutoring.",
            BODY,
        )
    )

    story.append(p("What <i>is</i> possible (panel-friendly as “our model”)", H1))
    story.append(
        p(
            "You can claim a <b>custom, domain-scoped model</b> if you mean one of these:",
            BODY,
        )
    )
    story.append(
        p(
            "<b>1. Rule-based / hybrid “model” (you already have pieces).</b> "
            "Explanation steps, calibration logic, adaptive selection, stubs when AI is off — "
            "this is <i>your</i> educational intelligence, not ChatGPT.",
            BULLET,
        )
    )
    story.append(
        p(
            "<b>2. Small fine-tune or classifier (realistic add-on).</b> "
            "e.g. error-type classifier or difficulty tagger on approved question bank + labeled mistakes "
            "(dozens–hundreds of examples), using a small open model or classic ML (sklearn + embeddings). "
            "Narrow task ≠ full generative AI.",
            BULLET,
        )
    )
    story.append(
        p(
            "<b>3. Self-host an open model (ops, not “we invented it”).</b> "
            "Run llama3.1:8b on a lab GPU/VM. Still someone else’s weights; you own <b>deployment</b>. "
            "Honest line: “self-hosted open-weight LLM,” not “we trained it.”",
            BULLET,
        )
    )
    story.append(
        p(
            "<b>4. Retrieval-augmented generation (RAG).</b> "
            "Generate feedback only from <i>your</i> approved explanations/topics — still uses an LLM "
            "API/local model, but the <b>knowledge is yours</b>. Stronger “we control quality” story.",
            BULLET,
        )
    )

    story.append(p("Honest answer for the panel", H1))
    story.append(
        p(
            "“Building a frontier generative model wasn’t feasible or necessary. What we <i>can</i> own "
            "is task-specific models or a small fine-tune later. For generation and tutoring we use an "
            "open/commercial LLM as the inference engine, with our prompts, normalization, and human "
            "approval. The thesis contribution is the SRL/calibration platform, not founding a new LLM.”",
            QUOTE,
        )
    )

    story.append(p("Practical verdict for ExamiQ now", H1))
    story.append(
        table(
            ["Goal", "Feasible now?"],
            [
                [
                    "Ship and defend the system",
                    "Use API/open LLM (what you do)",
                ],
                [
                    "Say “we made an AI model”",
                    "Only if you add a <b>small</b> custom piece (classifier / fine-tune / RAG) and describe it narrowly",
                ],
                [
                    "Replace Ollama entirely with a student-trained GPT",
                    "Not realistic in remaining thesis time",
                ],
            ],
            [7 * cm, 10 * cm],
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        p(
            "<b>Bottom line:</b> You don’t need to train GPT to have a valid AI thesis component. "
            "You <i>could</i> add a small custom model later for one task (e.g. error classification) "
            "if a panelist wants something “yours” — but redoing all generation as a homemade neural net "
            "is not a sensible path for this project.",
            BODY,
        )
    )
    story.append(
        p(
            "ExamiQ+ · Internal panel brief · Not for claiming false model ownership",
            FOOTNOTE,
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Is It Possible to Make Our Own AI/NLP Model?",
        author="ExamiQ+",
    )
    doc.build(story)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    build()

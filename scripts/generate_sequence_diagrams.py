#!/usr/bin/env python3
"""Render landscape ExamiQ sequence diagrams (two panels side-by-side with gap)."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PANELS = ROOT / "docs" / "thesis" / "panels"
OUTPUT_DIR = ROOT / "docs" / "thesis"
import shutil
import sys

_NPX = shutil.which("npx") or shutil.which("npx.cmd")
if not _NPX:
    raise SystemExit("npx not found; install Node.js to render Mermaid diagrams.")
MMDC = [_NPX, "--yes", "@mermaid-js/mermaid-cli@11.4.0"]

# Layout (landscape) — overall canvas size unchanged
CANVAS_W = 2200
CANVAS_H = 1180
MARGIN = 20
PANEL_GAP = 56
HEADER_H = 40
TITLE_H = 80
FOOTER_H = 72
PANEL_W = (CANVAS_W - 2 * MARGIN - PANEL_GAP) // 2
RENDER_W = int(PANEL_W * 3.2)  # high-res source for sharper zoom


def run_mmdc(mmd: Path, png: Path, width: int) -> None:
    subprocess.run(
        [
            *MMDC,
            "-i",
            str(mmd),
            "-o",
            str(png),
            "-b",
            "white",
            "-w",
            str(width),
        ],
        check=True,
        cwd=ROOT,
        shell=sys.platform == "win32",
    )


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def trim_white(img: Image.Image, padding: int = 12) -> Image.Image:
    rgb = img.convert("RGB")
    bg = rgb.getpixel((0, 0))
    w, h = rgb.size
    pixels = rgb.load()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            if pixels[x, y] != bg:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x or max_y <= min_y:
        return img
    return rgb.crop(
        (
            max(0, min_x - padding),
            max(0, min_y - padding),
            min(w, max_x + padding),
            min(h, max_y + padding),
        )
    )


def scale_panel(img: Image.Image, target_w: int, max_h: int) -> Image.Image:
    """Scale panel to fill column width; shrink only if taller than available area."""
    img = trim_white(img, padding=4)
    scale = target_w / img.width
    new_w = target_w
    new_h = int(img.height * scale)
    if new_h > max_h:
        scale = max_h / img.height
        new_w = int(img.width * scale)
        new_h = max_h
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_spacing: int = 4,
) -> int:
    avg_char = max(6, font.getlength("abcdefghijklmnopqrstuvwxyz") / 26)
    chars = max(20, int(max_width / avg_char))
    lines = textwrap.wrap(text, width=chars)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_spacing
    return y


def composite_diagram(
    left_png: Path,
    right_png: Path,
    output_png: Path,
    *,
    main_title: str,
    subtitle: str,
    left_title: str,
    right_title: str,
    left_color: tuple[int, int, int],
    right_color: tuple[int, int, int],
    role_text: str,
) -> None:
    left_raw = Image.open(left_png).convert("RGB")
    right_raw = Image.open(right_png).convert("RGB")

    panel_area_h = CANVAS_H - TITLE_H - FOOTER_H - MARGIN
    panel_inner_h = panel_area_h - HEADER_H - 6
    left = scale_panel(left_raw, PANEL_W, panel_inner_h)
    right = scale_panel(right_raw, PANEL_W, panel_inner_h)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), "white")
    draw = ImageDraw.Draw(canvas)

    title_font = load_font(24, bold=True)
    subtitle_font = load_font(12)
    panel_title_font = load_font(14, bold=True)
    body_font = load_font(11)

    title_w = draw.textlength(main_title, font=title_font)
    draw.text(((CANVAS_W - title_w) / 2, 18), main_title, font=title_font, fill=(17, 24, 39))
    sub_w = draw.textlength(subtitle, font=subtitle_font)
    draw.text(((CANVAS_W - sub_w) / 2, 52), subtitle, font=subtitle_font, fill=(75, 85, 99))

    panels_top = TITLE_H
    left_x = MARGIN
    right_x = MARGIN + PANEL_W + PANEL_GAP

    for idx, (panel_img, panel_x, title, color) in enumerate(
        [
            (left, left_x, left_title, left_color),
            (right, right_x, right_title, right_color),
        ]
    ):
        header_box = (panel_x, panels_top, panel_x + PANEL_W, panels_top + HEADER_H)
        draw.rectangle(header_box, fill=color)
        title_text = f"{idx + 1}. {title}"
        tw = draw.textlength(title_text, font=panel_title_font)
        draw.text(
            (panel_x + (PANEL_W - tw) / 2, panels_top + 10),
            title_text,
            font=panel_title_font,
            fill=(255, 255, 255),
        )

        inner_x = panel_x + (PANEL_W - panel_img.width) // 2
        inner_y = panels_top + HEADER_H + 4
        canvas.paste(panel_img, (inner_x, inner_y))

    footer_y = CANVAS_H - FOOTER_H + 8
    roles_font = load_font(11, bold=True)
    body_font = load_font(10)
    draw.text(
        (MARGIN, footer_y),
        "ACTORS AND ROLES",
        font=roles_font,
        fill=(17, 24, 39),
    )
    draw_wrapped(
        draw,
        role_text,
        (MARGIN, footer_y + 18),
        CANVAS_W - 2 * MARGIN,
        body_font,
        (31, 41, 55),
    )

    canvas.save(output_png, "PNG", optimize=True)


def main() -> None:
    PANELS.mkdir(parents=True, exist_ok=True)
    tmp = PANELS / "_rendered"
    tmp.mkdir(exist_ok=True)

    specs = {
        "campus-admin": PANELS / "campus-admin.mmd",
        "chairperson": PANELS / "chairperson.mmd",
        "student": PANELS / "student.mmd",
        "faculty": PANELS / "faculty.mmd",
    }
    rendered = {}
    for name, mmd in specs.items():
        out = tmp / f"{name}.png"
        run_mmdc(mmd, out, RENDER_W)
        rendered[name] = out

    composite_diagram(
        rendered["campus-admin"],
        rendered["chairperson"],
        OUTPUT_DIR / "sequence-diagram-admin-chairperson.png",
        main_title="Sequence Diagram for ExamiQ+",
        subtitle=(
            "A Self-Regulated Mathematics Exam Review System for College Students "
            "with Dynamic Feedback, Mistake Tracking, and Confidence-Based Test Flow"
        ),
        left_title="CAMPUS ADMIN PROCESSES",
        right_title="CHAIRPERSON PROCESSES",
        left_color=(37, 99, 235),
        right_color=(22, 163, 74),
        role_text=(
            "Campus Admin: Manages user accounts, program sections, and academic calendar; "
            "approves faculty and chairperson registrations. "
            "Chairperson: Assigns faculty to sections and subjects, monitors department analytics, "
            "and reviews audit logs and course participation."
        ),
    )

    composite_diagram(
        rendered["student"],
        rendered["faculty"],
        OUTPUT_DIR / "sequence-diagram-student-faculty.png",
        main_title="Sequence Diagram for ExamiQ+",
        subtitle=(
            "A Self-Regulated Mathematics Exam Review System for College Students "
            "with Dynamic Feedback, Mistake Tracking, and Confidence-Based Test Flow"
        ),
        left_title="STUDENT REVIEW AND ASSESSMENT",
        right_title="FACULTY PROCESSES",
        left_color=(124, 58, 237),
        right_color=(22, 163, 74),
        role_text=(
            "Student: Takes timed review sessions, submits answers with confidence signals, "
            "receives real-time feedback, and views performance summaries. "
            "Faculty: Configures exam setup, manages the question bank, and views "
            "course performance reports and intervention analytics."
        ),
    )

    print("Wrote:")
    print(f"  {OUTPUT_DIR / 'sequence-diagram-admin-chairperson.png'}")
    print(f"  {OUTPUT_DIR / 'sequence-diagram-student-faculty.png'}")


if __name__ == "__main__":
    main()

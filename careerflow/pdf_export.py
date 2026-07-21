from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from .core import CareerFlowError


def _font_candidates() -> List[Tuple[str, str]]:
    windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return [
        ("MicrosoftYaHei", str(windir / "msyh.ttc")),
        ("SimSun", str(windir / "simsun.ttc")),
        ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("Arial", str(windir / "arial.ttf")),
        ("Helvetica", ""),
    ]


def export_pdf(markdown: str, destination: Path) -> None:
    try:
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        raise CareerFlowError("PDF support is not installed. Run: pip install -e \".[pdf]\"")

    font_name = "Helvetica"
    for candidate, path in _font_candidates():
        if not path:
            font_name = candidate
            break
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(candidate, path))
                font_name = candidate
                break
            except Exception:
                continue

    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=13 * mm, bottomMargin=13 * mm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("ResumeNormal", parent=styles["BodyText"], fontName=font_name, fontSize=9.4, leading=12)
    h1 = ParagraphStyle("ResumeH1", parent=normal, fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=5)
    h2 = ParagraphStyle("ResumeH2", parent=normal, fontSize=12, leading=15, spaceBefore=9, spaceAfter=3)
    h3 = ParagraphStyle("ResumeH3", parent=normal, fontSize=10.5, leading=13, spaceBefore=5, spaceAfter=2)
    story = []
    bullets = []

    def flush_bullets() -> None:
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(item, normal)) for item in bullets], bulletType="bullet", leftIndent=13, bulletFontName=font_name))
            bullets[:] = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        flush_bullets()
        if line.startswith("### "):
            story.append(Paragraph(line[4:], h3))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], h2))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], h1))
        elif line:
            story.append(Paragraph(line, normal))
        else:
            story.append(Spacer(1, 2))
    flush_bullets()
    doc.build(story)

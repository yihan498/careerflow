from __future__ import annotations

import html
import os
import re
from pathlib import Path


DRAFT_FILES = {"resume.md", "cover-letter.md", "evidence-map.md"}
RESUME_SECTIONS = ["## Target", "## Education", "## Relevant Experience", "## Skills"]
INTERVIEW_SECTIONS = [
    "## 1. Evidence Boundary and Research Date",
    "## 2. Company Overview",
    "## 3. Relevant Business Workflow",
    "## 4. JD Decomposition",
    "## 5. Resume-to-Role Map",
    "## 6. Company and Role Questions",
    "## 7. Resume Follow-ups",
    "## 8. Mock Interview and Final Checklist",
    "## 9. Source Ledger",
]
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
RESERVED_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_draft_bundle(drafts: dict[str, str]) -> None:
    """Validate the stable CareerFlow draft contract inside the isolated web package."""
    _require(set(drafts) == DRAFT_FILES, "Draft bundle must contain exactly the three contracted files.")
    for name, content in drafts.items():
        _require(isinstance(content, str) and len(content.strip()) >= 40, f"{name} is empty or too short.")
        _require(len(content) <= 50_000, f"{name} exceeds the contracted size limit.")
        _require("```json" not in content.lower(), f"{name} contains an unparsed JSON wrapper.")
        _require("TODO" not in content, f"{name} contains an unresolved TODO placeholder.")
    _require(drafts["resume.md"].lstrip().startswith("# "), "Resume must start with one Markdown title.")
    positions: list[int] = []
    for heading in RESUME_SECTIONS:
        _require(drafts["resume.md"].count(heading) == 1, f"Resume must contain exactly one '{heading}' section.")
        positions.append(drafts["resume.md"].index(heading))
    _require(positions == sorted(positions), "Resume sections are out of contract order.")
    _require(
        drafts["cover-letter.md"].lstrip().startswith("# Cover Letter"),
        "Cover letter must use the contracted title.",
    )
    evidence = drafts["evidence-map.md"]
    _require(evidence.lstrip().startswith("# Evidence Map"), "Evidence map must use the contracted title.")
    _require(evidence.count("## Claim Mapping") == 1, "Evidence map must contain exactly one Claim Mapping section.")
    _require(evidence.count("## JD Gaps") == 1, "Evidence map must contain exactly one JD Gaps section.")
    _require(
        evidence.index("## Claim Mapping") < evidence.index("## JD Gaps"),
        "Evidence map sections are out of contract order.",
    )


def validate_interview_brief(
    brief: str,
    require_sources: bool,
    allowed_evidence_ids: set[str] | None = None,
) -> None:
    positions: list[int] = []
    for heading in INTERVIEW_SECTIONS:
        _require(brief.count(heading) == 1, f"Interview brief must contain exactly one '{heading}' section.")
        positions.append(brief.index(heading))
    _require(positions == sorted(positions), "Interview brief sections are out of contract order.")
    if require_sources:
        source_ledger = brief[brief.index("## 9. Source Ledger") :]
        _require(
            re.search(r"https?://[^\s)>]+", source_ledger) is not None,
            "Online interview source ledger must include source URLs.",
        )
        _require("TODO" not in brief, "Online interview research cannot contain TODO placeholders.")
        _require(
            any(label in brief for label in ("[Verified:", "[Inference]", "[Unknown]")),
            "Online interview findings must label their evidence status.",
        )
    allowed = allowed_evidence_ids or set()
    verified = re.findall(r"\[Verified:([A-Z0-9-]+)\]", brief)
    malformed_verified = "[Verified]" in brief or bool(re.search(r"\[Verified:(?![A-Z0-9-]+\])", brief))
    _require(not malformed_verified, "Verified claims must cite an evidence ID, for example [Verified:SRC-01].")
    _require(all(item in allowed for item in verified), "Interview brief cites an unverified evidence ID.")


def markdown_to_html(markdown: str, title: str) -> str:
    body: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if line.startswith("### "):
            body.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line:
            body.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        body.append("</ul>")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        "<style>@page{size:A4;margin:14mm}body{font-family:Arial,'Noto Sans CJK SC','Microsoft YaHei',sans-serif;"
        "color:#1f2937;line-height:1.42;max-width:780px;margin:auto}h1{font-size:25px;margin-bottom:4px}"
        "h2{font-size:16px;border-bottom:1px solid #94a3b8;padding-bottom:3px;margin-top:18px}"
        "h3{font-size:14px;margin-bottom:2px}p,li{font-size:11px;margin:3px 0}"
        "ul{margin:4px 0 8px;padding-left:20px}</style></head><body>"
        + "\n".join(body)
        + "</body></html>"
    )


def extract_jd_emails(jd: str) -> list[str]:
    seen: list[str] = []
    for match in EMAIL_PATTERN.findall(jd):
        normalized = match.strip().lower()
        if normalized not in seen:
            seen.append(normalized)
    return seen


def safe_attachment_name(value: str, extension: str) -> str:
    value = RESERVED_FILENAME.sub("-", value).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    if not value:
        raise ValueError("Attachment name cannot be empty.")
    suffix = extension.lower()
    if not value.lower().endswith(suffix):
        value += suffix
    if len(value) > 180:
        raise ValueError("Attachment filename is too long.")
    return value


def _font_candidates() -> list[tuple[str, str]]:
    windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return [
        ("MicrosoftYaHei", str(windir / "msyh.ttc")),
        ("SimSun", str(windir / "simsun.ttc")),
        ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("Arial", str(windir / "arial.ttf")),
        ("Helvetica", ""),
    ]


def export_pdf(markdown: str, destination: Path) -> None:
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

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
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("ResumeNormal", parent=styles["BodyText"], fontName=font_name, fontSize=9.4, leading=12)
    h1 = ParagraphStyle("ResumeH1", parent=normal, fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=5)
    h2 = ParagraphStyle("ResumeH2", parent=normal, fontSize=12, leading=15, spaceBefore=9, spaceAfter=3)
    h3 = ParagraphStyle("ResumeH3", parent=normal, fontSize=10.5, leading=13, spaceBefore=5, spaceAfter=2)
    story: list[object] = []
    bullets: list[str] = []

    def flush_bullets() -> None:
        if bullets:
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(html.escape(item), normal)) for item in bullets],
                    bulletType="bullet",
                    leftIndent=13,
                    bulletFontName=font_name,
                )
            )
            bullets.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        flush_bullets()
        if line.startswith("### "):
            story.append(Paragraph(html.escape(line[4:]), h3))
        elif line.startswith("## "):
            story.append(Paragraph(html.escape(line[3:]), h2))
        elif line.startswith("# "):
            story.append(Paragraph(html.escape(line[2:]), h1))
        elif line:
            story.append(Paragraph(html.escape(line), normal))
        else:
            story.append(Spacer(1, 2))
    flush_bullets()
    doc.build(story)

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from .core import CareerFlowError, load_json, slugify, utc_now, write_json


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
SUPPORTED_DOCUMENTS = {".pdf", ".docx"}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rgb_from_int(value: int) -> Tuple[float, float, float]:
    return (
        ((value >> 16) & 255) / 255.0,
        ((value >> 8) & 255) / 255.0,
        (value & 255) / 255.0,
    )


def _find_font() -> Optional[Path]:
    configured = os.environ.get("CAREERFLOW_FONT")
    candidates = [
        Path(configured) if configured else None,
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    return next((path for path in candidates if path and path.is_file()), None)


def inspect_pdf(source: Path) -> Dict[str, Any]:
    try:
        import fitz
    except ImportError:
        raise CareerFlowError("PDF template support is missing. Install: pip install -e \".[documents]\"")

    document = fitz.open(str(source))
    regions: List[Dict[str, Any]] = []
    for page_index, page in enumerate(document):
        page_regions: List[Dict[str, Any]] = []
        data = page.get_text("dict")
        line_index = 0
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if str(span.get("text", "")).strip()]
                if not spans:
                    continue
                text = "".join(str(span["text"]) for span in spans).strip()
                if not text:
                    continue
                x0 = min(float(span["bbox"][0]) for span in spans)
                y0 = min(float(span["bbox"][1]) for span in spans)
                x1 = max(float(span["bbox"][2]) for span in spans)
                y1 = max(float(span["bbox"][3]) for span in spans)
                primary = max(spans, key=lambda item: len(str(item.get("text", ""))))
                origin = primary.get("origin") or (x0, y1 - 1)
                region = {
                    "region_id": "pdf_p%03d_l%04d" % (page_index + 1, line_index + 1),
                    "page": page_index,
                    "text": text,
                    "bbox": [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)],
                    "origin": [round(float(origin[0]), 3), round(float(origin[1]), 3)],
                    "font_size": round(float(primary.get("size", 10)), 3),
                    "font_name": str(primary.get("font", "")),
                    "color": list(_rgb_from_int(int(primary.get("color", 0)))),
                    "span_count": len(spans),
                }
                page_regions.append(region)
                line_index += 1
        # Preserve the original left edge and use the next region on the same
        # baseline (or the page margin) as the available right boundary.
        for region in page_regions:
            x0, y0, _, y1 = region["bbox"]
            peers = [
                candidate for candidate in page_regions
                if candidate is not region
                and candidate["bbox"][0] > x0
                and abs(candidate["bbox"][1] - y0) <= max(2.5, region["font_size"] * 0.35)
            ]
            right = min((candidate["bbox"][0] - 3 for candidate in peers), default=float(page.rect.width) - 24)
            region["max_width"] = round(max(1.0, right - x0), 3)
            region["allowed_bbox"] = [round(x0 - 1.5, 3), round(y0 - 1.5, 3), round(right + 1.5, 3), round(y1 + 1.5, 3)]
            sample = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(region["allowed_bbox"]), alpha=False)
            channels = sample.n
            colors = Counter(
                tuple(sample.samples[offset:offset + channels][:3])
                for offset in range(0, len(sample.samples), channels)
            )
            background = colors.most_common(1)[0][0] if colors else (255, 255, 255)
            region["background_color"] = [round(value / 255.0, 4) for value in background]
        regions.extend(page_regions)
    pages = [{"page": index, "width": page.rect.width, "height": page.rect.height} for index, page in enumerate(document)]
    document.close()
    if not regions:
        raise CareerFlowError("No searchable text was found. Scanned PDFs need OCR before template registration.")
    return {"format": "pdf", "pages": pages, "regions": regions}


def _docx_parts(archive: zipfile.ZipFile) -> List[str]:
    return sorted(
        name for name in archive.namelist()
        if name == "word/document.xml"
        or (name.startswith("word/header") and name.endswith(".xml"))
        or (name.startswith("word/footer") and name.endswith(".xml"))
    )


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//{%s}t" % W_NS))


def inspect_docx(source: Path) -> Dict[str, Any]:
    regions: List[Dict[str, Any]] = []
    with zipfile.ZipFile(str(source), "r") as archive:
        for part in _docx_parts(archive):
            root = ET.fromstring(archive.read(part))
            paragraphs = root.findall(".//{%s}p" % W_NS)
            for index, paragraph in enumerate(paragraphs):
                text = _paragraph_text(paragraph).strip()
                if not text:
                    continue
                text_nodes = paragraph.findall(".//{%s}t" % W_NS)
                regions.append({
                    "region_id": "docx_%s_p%04d" % (Path(part).stem.replace(".", "-"), index + 1),
                    "part": part,
                    "paragraph_index": index,
                    "text": text,
                    "run_count": len(paragraph.findall(".//{%s}r" % W_NS)),
                    "text_node_count": len(text_nodes),
                })
    if not regions:
        raise CareerFlowError("No editable Word paragraphs were found.")
    return {"format": "docx", "regions": regions}


def inspect_document(source: Path, template_dir: Path, template_id: str) -> Path:
    source = source.expanduser().resolve()
    if slugify(template_id) != template_id:
        raise CareerFlowError("Template ID must be a safe lowercase slug.")
    if not source.is_file() or source.suffix.lower() not in SUPPORTED_DOCUMENTS:
        raise CareerFlowError("Template source must be a .pdf or .docx file.")
    if template_dir.exists():
        raise CareerFlowError("Template already exists: %s" % template_id)
    template_dir.mkdir(parents=True)
    original = template_dir / ("original" + source.suffix.lower())
    shutil.copy2(str(source), str(original))
    details = inspect_pdf(original) if source.suffix.lower() == ".pdf" else inspect_docx(original)
    profile = {
        "schema_version": 1,
        "template_id": template_id,
        "source_file": original.name,
        "source_sha256": file_sha256(original),
        "created_at": utc_now(),
        **details,
    }
    write_json(template_dir / "document-profile.json", profile)
    if profile["format"] == "pdf":
        _render_pdf(original, template_dir / "baseline.png")
    return template_dir / "document-profile.json"


def create_plan(template_dir: Path, destination: Path) -> Path:
    profile = load_json(template_dir / "document-profile.json")
    write_json(destination, {
        "schema_version": 1,
        "template_id": profile["template_id"],
        "source_sha256": profile["source_sha256"],
        "changes": [],
        "instructions": "Add only user-approved replacements: {region_id, old_text, new_text}. Keep each PDF replacement on one original line.",
    })
    return destination


def _validate_plan(profile: Dict[str, Any], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    if plan.get("template_id") != profile.get("template_id"):
        raise CareerFlowError("Document plan targets a different template.")
    if plan.get("source_sha256") != profile.get("source_sha256"):
        raise CareerFlowError("Source document changed after inspection.")
    changes = plan.get("changes")
    if not isinstance(changes, list) or not changes:
        raise CareerFlowError("Document plan must contain at least one approved change.")
    regions = {item["region_id"]: item for item in profile["regions"]}
    seen = set()
    normalized = []
    for change in changes:
        region_id = change.get("region_id")
        if region_id in seen or region_id not in regions:
            raise CareerFlowError("Unknown or duplicate document region: %s" % region_id)
        seen.add(region_id)
        region = regions[region_id]
        old_text = str(change.get("old_text", ""))
        new_text = str(change.get("new_text", "")).strip()
        if old_text != region["text"]:
            raise CareerFlowError("Old text does not match inspected source for %s." % region_id)
        if not new_text:
            raise CareerFlowError("Replacement text cannot be empty: %s" % region_id)
        normalized.append({"region": region, "old_text": old_text, "new_text": new_text})
    return normalized


def _render_pdf(source: Path, destination: Path, scale: float = 2.0) -> None:
    import fitz
    document = fitz.open(str(source))
    if len(document) != 1:
        # A contact sheet would hide defects. Keep page previews separate.
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pixmap.save(str(destination.with_name("%s-p%03d%s" % (destination.stem, index + 1, destination.suffix))))
    else:
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        pixmap.save(str(destination))
    document.close()


def _pdf_preview_paths(base: Path, page_count: int) -> List[Path]:
    if page_count == 1:
        return [base]
    return [base.with_name("%s-p%03d%s" % (base.stem, index + 1, base.suffix)) for index in range(page_count)]


def _pdf_font_choice(region: Dict[str, Any]):
    import fitz
    original = str(region.get("font_name", "")).lower()
    if "times" in original:
        return fitz.Font("tiro"), {"fontname": "tiro"}, "Times-compatible"
    if "courier" in original or "mono" in original:
        return fitz.Font("cour"), {"fontname": "cour"}, "Courier-compatible"
    if "helvetica" in original or "arial" in original:
        return fitz.Font("helv"), {"fontname": "helv"}, "Helvetica-compatible"
    font_path = _find_font()
    if font_path:
        return fitz.Font(fontfile=str(font_path)), {"fontfile": str(font_path), "fontname": "careerflow"}, str(font_path)
    return fitz.Font("helv"), {"fontname": "helv"}, "Helvetica fallback"


def validate_document_plan(template_dir: Path, plan_path: Path) -> Dict[str, Any]:
    profile = load_json(template_dir / "document-profile.json")
    plan = load_json(plan_path)
    source = template_dir / profile["source_file"]
    if file_sha256(source) != profile["source_sha256"]:
        raise CareerFlowError("Registered source document has changed.")
    changes = _validate_plan(profile, plan)
    if profile["format"] == "pdf":
        for item in changes:
            font, _, _ = _pdf_font_choice(item["region"])
            width = font.text_length(item["new_text"], fontsize=float(item["region"]["font_size"]))
            if width > float(item["region"]["max_width"]):
                raise CareerFlowError(
                    "Replacement exceeds the original line capacity for %s (%.1f > %.1f points)."
                    % (item["region"]["region_id"], width, item["region"]["max_width"])
                )
    return {"format": profile["format"], "change_count": len(changes), "status": "valid"}


def apply_pdf(template_dir: Path, profile: Dict[str, Any], plan: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    try:
        import fitz
        from PIL import Image, ImageChops, ImageDraw
    except ImportError:
        raise CareerFlowError("PDF editor dependencies are missing. Install: pip install -e \".[documents]\"")
    changes = _validate_plan(profile, plan)
    source = template_dir / profile["source_file"]
    document = fitz.open(str(source))
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    font_mappings = {}
    for item in changes:
        by_page.setdefault(int(item["region"]["page"]), []).append(item)
        fitz_font, font_kwargs, mapping = _pdf_font_choice(item["region"])
        item["font_kwargs"] = font_kwargs
        font_mappings[item["region"]["region_id"]] = mapping
        width = fitz_font.text_length(item["new_text"], fontsize=float(item["region"]["font_size"]))
        if width > float(item["region"]["max_width"]):
            raise CareerFlowError(
                "Replacement exceeds the original line capacity for %s (%.1f > %.1f points). Rewrite it before build."
                % (item["region"]["region_id"], width, item["region"]["max_width"])
            )
    for page_index, page_changes in by_page.items():
        page = document[page_index]
        for item in page_changes:
            rect = fitz.Rect(item["region"]["allowed_bbox"])
            page.add_redact_annot(rect, fill=tuple(item["region"].get("background_color", (1, 1, 1))), cross_out=False)
        try:
            page.apply_redactions(graphics=0)
        except TypeError:
            page.apply_redactions()
        for item in page_changes:
            region = item["region"]
            page.insert_text(
                tuple(region["origin"]),
                item["new_text"],
                fontsize=float(region["font_size"]),
                color=tuple(region["color"]),
                overlay=True,
                **item["font_kwargs"]
            )
    output_pdf = output_dir / "tailored-resume.pdf"
    document.save(str(output_pdf), garbage=4, deflate=True)
    page_count = len(document)
    document.close()

    source_preview = output_dir / "source-preview.png"
    output_preview = output_dir / "tailored-resume.png"
    _render_pdf(source, source_preview)
    _render_pdf(output_pdf, output_preview)
    source_images = _pdf_preview_paths(source_preview, page_count)
    output_images = _pdf_preview_paths(output_preview, page_count)
    outside_pixels = 0
    total_pixels = 0
    diff_paths = []
    for page_index, (before_path, after_path) in enumerate(zip(source_images, output_images)):
        before = Image.open(str(before_path)).convert("RGB")
        after = Image.open(str(after_path)).convert("RGB")
        diff = ImageChops.difference(before, after)
        mask = Image.new("L", before.size, 0)
        draw = ImageDraw.Draw(mask)
        for item in by_page.get(page_index, []):
            x0, y0, x1, y1 = item["region"]["allowed_bbox"]
            draw.rectangle((int((x0 - 2) * 2), int((y0 - 2) * 2), int((x1 + 2) * 2), int((y1 + 2) * 2)), fill=255)
        outside = Image.composite(Image.new("RGB", diff.size), diff, mask)
        diff_path = output_dir / ("outside-diff-p%03d.png" % (page_index + 1))
        outside.save(str(diff_path))
        diff_paths.append(diff_path.name)
        pixels = outside.convert("L")
        outside_pixels += sum(pixels.histogram()[9:])
        total_pixels += pixels.width * pixels.height
    ratio = outside_pixels / float(total_pixels or 1)
    if ratio > 0.00005:
        raise CareerFlowError("Visual validation found changes outside approved regions (ratio %.8f)." % ratio)

    check = fitz.open(str(output_pdf))
    missing = []
    for item in changes:
        page = check[int(item["region"]["page"])]
        text = page.get_text("text", clip=fitz.Rect(item["region"]["allowed_bbox"]))
        if "".join(item["new_text"].split()) not in "".join(text.split()):
            missing.append(item["region"]["region_id"])
    check.close()
    if missing:
        raise CareerFlowError("Replacement text is not searchable in regions: %s" % ", ".join(missing))
    return {
        "format": "pdf",
        "output": output_pdf.name,
        "previews": [path.name for path in output_images],
        "outside_diff_previews": diff_paths,
        "outside_changed_pixel_ratio": ratio,
        "searchable_text_check": "passed",
        "font_mappings": font_mappings,
        "visual_qa_required": True,
    }


def apply_docx(template_dir: Path, profile: Dict[str, Any], plan: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    changes = _validate_plan(profile, plan)
    source = template_dir / profile["source_file"]
    output_docx = output_dir / "tailored-resume.docx"
    change_map = {item["region"]["region_id"]: item for item in changes}
    region_map = {item["region_id"]: item for item in profile["regions"]}
    part_changes: Dict[str, Dict[int, str]] = {}
    for region_id, item in change_map.items():
        region = region_map[region_id]
        part_changes.setdefault(region["part"], {})[int(region["paragraph_index"])] = item["new_text"]
    with zipfile.ZipFile(str(source), "r") as incoming, zipfile.ZipFile(str(output_docx), "w") as outgoing:
        for info in incoming.infolist():
            data = incoming.read(info.filename)
            if info.filename in part_changes:
                root = ET.fromstring(data)
                paragraphs = root.findall(".//{%s}p" % W_NS)
                for index, new_text in part_changes[info.filename].items():
                    nodes = paragraphs[index].findall(".//{%s}t" % W_NS)
                    if not nodes:
                        raise CareerFlowError("Word region has no writable text node.")
                    nodes[0].text = new_text
                    nodes[0].set("{%s}space" % XML_NS, "preserve")
                    for node in nodes[1:]:
                        node.text = ""
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            outgoing.writestr(info, data)
    updated = inspect_docx(output_docx)
    updated_regions = {item["region_id"]: item for item in updated["regions"]}
    failed = [region_id for region_id, item in change_map.items() if updated_regions.get(region_id, {}).get("text") != item["new_text"]]
    if failed:
        raise CareerFlowError("Word replacement validation failed: %s" % ", ".join(failed))
    return {
        "format": "docx",
        "output": output_docx.name,
        "structure_check": "passed",
        "visual_qa_required": True,
        "visual_qa_note": "Render the DOCX with Microsoft Word or LibreOffice and inspect pagination, text boxes, tables and glyphs.",
    }


def apply_document(template_dir: Path, plan_path: Path, output_dir: Path) -> Path:
    validate_document_plan(template_dir, plan_path)
    profile = load_json(template_dir / "document-profile.json")
    plan = load_json(plan_path)
    source = template_dir / profile["source_file"]
    if file_sha256(source) != profile["source_sha256"]:
        raise CareerFlowError("Registered source document has changed.")
    output_dir.mkdir(parents=True, exist_ok=True)
    if profile["format"] == "pdf":
        result = apply_pdf(template_dir, profile, plan, output_dir)
    elif profile["format"] == "docx":
        result = apply_docx(template_dir, profile, plan, output_dir)
    else:
        raise CareerFlowError("Unsupported registered document format.")
    result.update({
        "template_id": profile["template_id"],
        "source_sha256": profile["source_sha256"],
        "plan_sha256": file_sha256(plan_path),
        "built_at": utc_now(),
    })
    result_path = output_dir / "document-edit-result.json"
    write_json(result_path, result)
    return result_path

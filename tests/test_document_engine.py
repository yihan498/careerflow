import json
import zipfile
from pathlib import Path

from careerflow.core import Workspace, approve_application, build_application, draft_application
from careerflow.core import CareerFlowError
from careerflow.document_engine import apply_document, create_plan, inspect_document


def _write_plan(path: Path, profile: dict, region: dict, new_text: str) -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "template_id": profile["template_id"],
        "source_sha256": profile["source_sha256"],
        "changes": [{
            "region_id": region["region_id"],
            "old_text": region["text"],
            "new_text": new_text,
        }],
    }), encoding="utf-8")


def test_pdf_template_is_inspected_edited_and_visually_bounded(tmp_path):
    from reportlab.pdfgen import canvas

    source = tmp_path / "resume.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(595, 842))
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 760, "Original analyst bullet")
    pdf.drawString(72, 720, "Untouched education line")
    pdf.save()
    template = tmp_path / "templates" / "default"
    profile_path = inspect_document(source, template, "default")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    region = next(item for item in profile["regions"] if item["text"] == "Original analyst bullet")
    plan = tmp_path / "plan.json"
    _write_plan(plan, profile, region, "Tailored analyst bullet")
    result_path = apply_document(template, plan, tmp_path / "output")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["format"] == "pdf"
    assert result["searchable_text_check"] == "passed"
    assert result["outside_changed_pixel_ratio"] <= 0.00005
    assert (tmp_path / "output" / "tailored-resume.pdf").exists()
    assert (tmp_path / "output" / "tailored-resume.png").exists()


def _create_minimal_docx(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>Original project bullet</w:t></w:r></w:p>
    <w:p><w:r><w:t>Untouched skills line</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(str(path), "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)


def test_docx_template_replaces_text_without_rebuilding_package(tmp_path):
    source = tmp_path / "resume.docx"
    _create_minimal_docx(source)
    template = tmp_path / "templates" / "default"
    profile_path = inspect_document(source, template, "default")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    region = next(item for item in profile["regions"] if item["text"] == "Original project bullet")
    plan = tmp_path / "plan.json"
    _write_plan(plan, profile, region, "Tailored project bullet")
    result_path = apply_document(template, plan, tmp_path / "output")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["format"] == "docx"
    assert result["structure_check"] == "passed"
    with zipfile.ZipFile(str(tmp_path / "output" / "tailored-resume.docx")) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "Tailored project bullet" in xml
    assert "Untouched skills line" in xml


def test_plan_skeleton_binds_template_hash(tmp_path):
    source = tmp_path / "resume.docx"
    _create_minimal_docx(source)
    template = tmp_path / "templates" / "default"
    inspect_document(source, template, "default")
    plan_path = create_plan(template, tmp_path / "document-plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    profile = json.loads((template / "document-profile.json").read_text(encoding="utf-8"))
    assert plan["source_sha256"] == profile["source_sha256"]
    assert plan["changes"] == []


def test_application_build_invokes_registered_pdf_editor(tmp_path):
    from reportlab.pdfgen import canvas

    source = tmp_path / "candidate.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(595, 842))
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 760, "Original analyst bullet")
    pdf.save()
    root = Path(__file__).resolve().parents[1]
    demo = root / "examples" / "demo"
    workspace = Workspace(tmp_path / "runtime")
    workspace.add_user(demo / "profile.json", source)
    app = workspace.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", demo / "jd.md")
    draft_application(workspace, app.name, "rules")
    plan_path = create_plan(workspace.user_dir("demo-candidate") / "templates" / "default", app / "draft" / "document-plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    profile = json.loads((workspace.user_dir("demo-candidate") / "templates" / "default" / "document-profile.json").read_text(encoding="utf-8"))
    region = profile["regions"][0]
    plan["changes"] = [{"region_id": region["region_id"], "old_text": region["text"], "new_text": "Tailored analyst bullet"}]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    approve_application(workspace, app.name, "reviewer")
    output = build_application(workspace, app.name, no_pdf=True)
    result = json.loads((output / "document-edit-result.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert result["searchable_text_check"] == "passed"
    assert manifest["original_format_result"] == "document-edit-result.json"
    assert (output / "tailored-resume.pdf").exists()


def test_registered_document_cannot_bypass_original_format_plan(tmp_path):
    from reportlab.pdfgen import canvas
    import pytest

    source = tmp_path / "candidate.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(595, 842))
    pdf.drawString(72, 760, "Original bullet")
    pdf.save()
    root = Path(__file__).resolve().parents[1]
    demo = root / "examples" / "demo"
    workspace = Workspace(tmp_path / "runtime")
    workspace.add_user(demo / "profile.json", source)
    app = workspace.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", demo / "jd.md")
    draft_application(workspace, app.name, "rules")
    with pytest.raises(CareerFlowError, match="original PDF/DOCX"):
        approve_application(workspace, app.name, "reviewer")

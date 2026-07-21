import json
from pathlib import Path

import pytest

from careerflow.contracts import validate_draft_bundle, validate_interview_brief
from careerflow.core import Workspace, approve_application, build_application, draft_application, prepare_interview


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"


def test_draft_contract_rejects_missing_gap_section():
    drafts = {
        "resume.md": "# Candidate\n\n## Target\nRole\n## Education\nSchool\n## Relevant Experience\nA sufficiently detailed confirmed experience entry.\n## Skills\nAnalysis",
        "cover-letter.md": "# Cover Letter\n\nA sufficiently detailed evidence-based application letter.",
        "evidence-map.md": "# Evidence Map\n\n## Claim Mapping\n\nA claim maps to experience-1.",
    }
    with pytest.raises(ValueError, match="JD Gaps"):
        validate_draft_bundle(drafts)


def test_online_interview_contract_rejects_unstructured_output():
    with pytest.raises(ValueError, match="Evidence Boundary"):
        validate_interview_brief("A free-form interview essay with https://example.invalid", require_sources=True)


def test_rule_outputs_write_validated_contract_manifests(tmp_path):
    workspace = Workspace(tmp_path / "runtime")
    workspace.add_user(DEMO / "profile.json", DEMO / "source-resume.md")
    app = workspace.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", DEMO / "jd.md")
    draft_application(workspace, app.name, "rules")
    draft_manifest = json.loads((app / "draft" / "agent-output-contract.json").read_text(encoding="utf-8"))
    assert draft_manifest["status"] == "structure_validated_human_approval_required"
    approve_application(workspace, app.name, "reviewer")
    build_application(workspace, app.name, no_pdf=True)
    prepare_interview(workspace, app.name, "rules")
    interview_manifest = json.loads((app / "interview" / "manifest.json").read_text(encoding="utf-8"))
    assert interview_manifest["status"] == "structure_validated_human_review_required"


def test_submitted_application_can_enter_interview_stage(tmp_path):
    workspace = Workspace(tmp_path / "runtime")
    workspace.add_user(DEMO / "profile.json")
    app = workspace.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", DEMO / "jd.md")
    draft_application(workspace, app.name, "rules")
    approve_application(workspace, app.name, "reviewer")
    build_application(workspace, app.name, no_pdf=True)
    workspace.transition(app, "submitted", {"built"})
    prepare_interview(workspace, app.name, "rules")
    assert workspace.meta(app)["stage"] == "interviewing"

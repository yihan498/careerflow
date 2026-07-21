from pathlib import Path

import pytest

from careerflow.core import (
    CareerFlowError,
    Workspace,
    approve_application,
    build_application,
    draft_application,
    prepare_interview,
    record_review,
)


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"


def test_complete_offline_workflow(tmp_path):
    ws = Workspace(tmp_path / "runtime")
    ws.add_user(DEMO / "profile.json", DEMO / "source-resume.md")
    app = ws.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", DEMO / "jd.md")
    draft_application(ws, app.name, "rules")
    approve_application(ws, app.name, "reviewer")
    output = build_application(ws, app.name, no_pdf=True)
    interview = prepare_interview(ws, app.name, "rules")
    review = record_review(ws, app.name, "rejected", DEMO / "review-notes.md")
    assert (output / "resume.html").exists()
    assert interview.exists()
    assert review.exists()
    assert ws.meta(app)["stage"] == "closed"
    assert len(ws.list_applications()) == 1


def test_approval_hash_blocks_changed_draft(tmp_path):
    ws = Workspace(tmp_path / "runtime")
    ws.add_user(DEMO / "profile.json")
    app = ws.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", DEMO / "jd.md")
    draft_application(ws, app.name, "rules")
    approve_application(ws, app.name, "reviewer")
    resume = app / "draft" / "resume.md"
    resume.write_text(resume.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    with pytest.raises(CareerFlowError, match="changed after approval"):
        build_application(ws, app.name, no_pdf=True)


def test_users_are_isolated(tmp_path):
    ws = Workspace(tmp_path / "runtime")
    ws.add_user(DEMO / "profile.json")
    assert (ws.root / "users" / "demo-candidate" / "profile" / "evidence.json").exists()
    assert ws.root != ROOT
    assert ROOT not in ws.root.parents

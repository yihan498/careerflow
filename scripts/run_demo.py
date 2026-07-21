from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from careerflow.core import (  # noqa: E402
    Workspace,
    approve_application,
    build_application,
    draft_application,
    prepare_interview,
    record_review,
)
from careerflow.document_engine import create_plan  # noqa: E402


def main() -> int:
    target = Path(tempfile.mkdtemp(prefix="careerflow-demo-"))
    demo = ROOT / "examples" / "demo"
    try:
        ws = Workspace(target)
        ws.bootstrap()
        from reportlab.pdfgen import canvas
        source_pdf = target / "fictional-source-resume.pdf"
        pdf = canvas.Canvas(str(source_pdf), pagesize=(595, 842))
        pdf.setFont("Helvetica", 11)
        pdf.drawString(72, 760, "Original product operations bullet")
        pdf.save()
        ws.add_user(demo / "profile.json", source_pdf)
        app = ws.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", demo / "jd.md")
        app_id = app.name
        draft_application(ws, app_id, "rules")
        plan_path = create_plan(ws.user_dir("demo-candidate") / "templates" / "default", app / "draft" / "document-plan.json")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        profile = json.loads((ws.user_dir("demo-candidate") / "templates" / "default" / "document-profile.json").read_text(encoding="utf-8"))
        region = profile["regions"][0]
        plan["changes"] = [{
            "region_id": region["region_id"],
            "old_text": region["text"],
            "new_text": "Tailored product operations bullet",
        }]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        approve_application(ws, app_id, "demo-user")
        build_application(ws, app_id, no_pdf=True)
        prepare_interview(ws, app_id, "rules")
        record_review(ws, app_id, "rejected", demo / "review-notes.md")
        assert ws.meta(app)["stage"] == "closed"
        assert (target / "aggregate" / "review-summary.md").exists()
        assert (app / "output" / "tailored-resume.pdf").exists()
        print("PASS: complete offline workflow")
        print("Temporary workspace: %s" % target)
        return 0
    except Exception:
        shutil.rmtree(str(target), ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())

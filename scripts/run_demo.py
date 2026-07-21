from __future__ import annotations

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


def main() -> int:
    target = Path(tempfile.mkdtemp(prefix="careerflow-demo-"))
    demo = ROOT / "examples" / "demo"
    try:
        ws = Workspace(target)
        ws.bootstrap()
        ws.add_user(demo / "profile.json", demo / "source-resume.md")
        app = ws.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", demo / "jd.md")
        app_id = app.name
        draft_application(ws, app_id, "rules")
        approve_application(ws, app_id, "demo-user")
        build_application(ws, app_id, no_pdf=True)
        prepare_interview(ws, app_id, "rules")
        record_review(ws, app_id, "rejected", demo / "review-notes.md")
        assert ws.meta(app)["stage"] == "closed"
        assert (target / "aggregate" / "review-summary.md").exists()
        print("PASS: complete offline workflow")
        print("Temporary workspace: %s" % target)
        return 0
    except Exception:
        shutil.rmtree(str(target), ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())

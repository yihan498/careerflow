from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import (
    CareerFlowError,
    Workspace,
    approve_application,
    build_application,
    draft_application,
    prepare_interview,
    record_review,
    slugify,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="careerflow", description="Privacy-first job application workflow")
    root.add_argument("--workspace", help="Runtime workspace; defaults to CAREERFLOW_HOME or ~/.careerflow")
    sub = root.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="Create an isolated runtime workspace")
    user = sub.add_parser("user-add", help="Initialize one user's confirmed evidence library")
    user.add_argument("--profile", type=Path, required=True)
    user.add_argument("--resume", type=Path)

    inspect = sub.add_parser("template-inspect", help="Register and inspect a private PDF or DOCX resume template")
    inspect.add_argument("--user", required=True)
    inspect.add_argument("--source", type=Path, required=True)
    inspect.add_argument("--template-id", default="default")

    apply = sub.add_parser("apply", help="Create one isolated application branch")
    apply.add_argument("--user", required=True)
    apply.add_argument("--company", required=True)
    apply.add_argument("--role", required=True)
    apply.add_argument("--jd", type=Path, required=True)

    draft = sub.add_parser("draft", help="Create resume, cover letter and evidence map")
    draft.add_argument("--application", required=True)
    draft.add_argument("--provider", choices=["rules", "openai"], default="rules")

    plan = sub.add_parser("template-plan", help="Create an original-format replacement plan for agent completion")
    plan.add_argument("--application", required=True)
    plan.add_argument("--template-id", default="default")

    approve = sub.add_parser("approve", help="Lock user-approved drafts")
    approve.add_argument("--application", required=True)
    approve.add_argument("--confirmed-by", required=True)

    build = sub.add_parser("build", help="Build approved application artifacts")
    build.add_argument("--application", required=True)
    build.add_argument("--no-pdf", action="store_true")

    interview = sub.add_parser("interview", help="Research the company and prepare predicted questions")
    interview.add_argument("--application", required=True)
    interview.add_argument("--provider", choices=["rules", "openai"], default="rules")

    review = sub.add_parser("review", help="Record outcome and sync learning to the aggregate review")
    review.add_argument("--application", required=True)
    review.add_argument("--outcome", choices=["rejected", "withdrew", "offer", "pending"], required=True)
    review.add_argument("--notes", type=Path, required=True)

    sub.add_parser("status", help="List all applications and their stages")
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    workspace = Workspace.from_value(args.workspace)
    try:
        if args.command == "bootstrap":
            print(workspace.bootstrap())
        elif args.command == "user-add":
            print(workspace.add_user(args.profile, args.resume))
        elif args.command == "template-inspect":
            from .document_engine import inspect_document
            workspace.profile(args.user)
            template_id = slugify(args.template_id)
            destination = workspace.user_dir(args.user) / "templates" / template_id
            print(inspect_document(args.source, destination, template_id))
        elif args.command == "apply":
            print(workspace.create_application(args.user, args.company, args.role, args.jd))
        elif args.command == "draft":
            print(draft_application(workspace, args.application, args.provider))
        elif args.command == "template-plan":
            from .document_engine import create_plan
            app_dir = workspace.find_application(args.application)
            meta = workspace.meta(app_dir)
            if meta["stage"] != "drafted":
                raise CareerFlowError("Create the document plan after drafting and before approval.")
            template_id = slugify(args.template_id)
            template_dir = workspace.user_dir(meta["user_id"]) / "templates" / template_id
            print(create_plan(template_dir, app_dir / "draft" / "document-plan.json"))
        elif args.command == "approve":
            print(approve_application(workspace, args.application, args.confirmed_by))
        elif args.command == "build":
            print(build_application(workspace, args.application, args.no_pdf))
        elif args.command == "interview":
            print(prepare_interview(workspace, args.application, args.provider))
        elif args.command == "review":
            print(record_review(workspace, args.application, args.outcome, args.notes))
        elif args.command == "status":
            workspace.bootstrap()
            rows = workspace.list_applications()
            if not rows:
                print("No applications.")
            for item in rows:
                print("{application_id}\t{stage}\t{company}\t{role}".format(**item))
        return 0
    except CareerFlowError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

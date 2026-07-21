import json
from pathlib import Path

import pytest

from careerflow.core import CareerFlowError, Workspace, approve_application, build_application, draft_application
from careerflow.email_delivery import approve_email, extract_jd_emails, prepare_email, send_email


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"


def _built_application(tmp_path):
    workspace = Workspace(tmp_path / "runtime")
    workspace.add_user(DEMO / "profile.json", DEMO / "source-resume.md")
    jd = tmp_path / "jd.md"
    jd.write_text((DEMO / "jd.md").read_text(encoding="utf-8") + "\nApply via hr@example.invalid.\n", encoding="utf-8")
    app = workspace.create_application("demo-candidate", "Northstar Labs", "Product Operations Intern", jd)
    draft_application(workspace, app.name, "rules")
    approve_application(workspace, app.name, "reviewer")
    build_application(workspace, app.name)
    return workspace, app


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=30, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.logged_in = None
        self.message = None
        self.tls = False
        self.closed = False
        self.__class__.instances.append(self)

    def ehlo(self):
        return None

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.message = message
        return {}

    def quit(self):
        self.closed = True


def test_jd_email_extraction_is_unique_and_normalized():
    assert extract_jd_emails("Send to HR@Example.invalid and hr@example.invalid") == ["hr@example.invalid"]


def test_prepare_approve_and_send_once(tmp_path, monkeypatch):
    workspace, app = _built_application(tmp_path)
    plan_path = prepare_email(workspace, app.name, sender="alex@example.invalid")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["to"] == "hr@example.invalid"
    assert plan["subject"] == Path(plan["attachment_filename"]).stem
    assert plan["recipient_source"] == "job_description"
    assert (app / "delivery" / "email-preview.eml").exists()
    approval_path = approve_email(workspace, app.name, "user-confirmed")
    code = json.loads(approval_path.read_text(encoding="utf-8"))["confirmation_code"]

    monkeypatch.setenv("CAREERFLOW_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("CAREERFLOW_SMTP_USER", "alex@example.invalid")
    monkeypatch.setenv("CAREERFLOW_SMTP_PASSWORD", "app-password-for-test")
    monkeypatch.setenv("CAREERFLOW_SMTP_SECURITY", "starttls")
    receipt_path = send_email(workspace, app.name, code, smtp_factory=FakeSMTP)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "sent"
    assert workspace.meta(app)["stage"] == "submitted"
    assert FakeSMTP.instances[-1].tls is True
    assert FakeSMTP.instances[-1].message["Subject"] == plan["subject"]
    assert len(list(FakeSMTP.instances[-1].message.iter_attachments())) == 1
    with pytest.raises(CareerFlowError, match="exactly once"):
        send_email(workspace, app.name, code, smtp_factory=FakeSMTP)


def test_multiple_jd_emails_require_explicit_recipient(tmp_path):
    workspace, app = _built_application(tmp_path)
    jd_path = app / "input" / "jd.md"
    jd_path.write_text(jd_path.read_text(encoding="utf-8") + "\nCC team@example.invalid\n", encoding="utf-8")
    with pytest.raises(CareerFlowError, match="Multiple email addresses"):
        prepare_email(workspace, app.name, sender="alex@example.invalid")


def test_manual_recipient_must_come_from_jd(tmp_path):
    workspace, app = _built_application(tmp_path)
    with pytest.raises(CareerFlowError, match="not one of"):
        prepare_email(workspace, app.name, recipient="wrong@example.invalid", sender="alex@example.invalid")


def test_changed_attachment_is_blocked_after_approval(tmp_path, monkeypatch):
    workspace, app = _built_application(tmp_path)
    plan_path = prepare_email(workspace, app.name, sender="alex@example.invalid")
    approval_path = approve_email(workspace, app.name, "user-confirmed")
    code = json.loads(approval_path.read_text(encoding="utf-8"))["confirmation_code"]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    attachment = app / "delivery" / plan["attachment_relative_path"]
    attachment.write_bytes(attachment.read_bytes() + b"changed")
    monkeypatch.setenv("CAREERFLOW_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("CAREERFLOW_SMTP_USER", "alex@example.invalid")
    monkeypatch.setenv("CAREERFLOW_SMTP_PASSWORD", "test")
    with pytest.raises(CareerFlowError, match="changed after approval"):
        send_email(workspace, app.name, code, smtp_factory=FakeSMTP)


def test_wrong_confirmation_code_is_blocked_before_smtp(tmp_path, monkeypatch):
    workspace, app = _built_application(tmp_path)
    prepare_email(workspace, app.name, sender="alex@example.invalid")
    approve_email(workspace, app.name, "user-confirmed")
    with pytest.raises(CareerFlowError, match="confirmation code"):
        send_email(workspace, app.name, "WRONG-CODE", smtp_factory=FakeSMTP)
    assert not (app / "delivery" / "send-attempt.json").exists()


class FailingSMTP(FakeSMTP):
    def send_message(self, message):
        raise OSError("connection status unknown")


def test_uncertain_attempt_blocks_automatic_retry(tmp_path, monkeypatch):
    workspace, app = _built_application(tmp_path)
    prepare_email(workspace, app.name, sender="alex@example.invalid")
    approval_path = approve_email(workspace, app.name, "user-confirmed")
    code = json.loads(approval_path.read_text(encoding="utf-8"))["confirmation_code"]
    monkeypatch.setenv("CAREERFLOW_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("CAREERFLOW_SMTP_USER", "alex@example.invalid")
    monkeypatch.setenv("CAREERFLOW_SMTP_PASSWORD", "test")
    with pytest.raises(CareerFlowError, match="uncertain"):
        send_email(workspace, app.name, code, smtp_factory=FailingSMTP)
    attempt = json.loads((app / "delivery" / "send-attempt.json").read_text(encoding="utf-8"))
    assert attempt["status"] == "uncertain"
    with pytest.raises(CareerFlowError, match="retry is blocked"):
        send_email(workspace, app.name, code, smtp_factory=FakeSMTP)

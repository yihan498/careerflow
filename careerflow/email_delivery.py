from __future__ import annotations

import hashlib
import os
import re
import shutil
import smtplib
import ssl
import uuid
import zipfile
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import CareerFlowError, Workspace, load_json, read_text, utc_now, write_json


EMAIL_PATTERN = re.compile(
    r"(?<![A-Z0-9._%+-])([A-Z0-9._%+-]+@(?:[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\.)+[A-Z]{2,})(?![A-Z0-9_%+-])",
    re.I,
)
RESERVED_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_jd_emails(jd: str) -> List[str]:
    seen = []
    for match in EMAIL_PATTERN.findall(jd):
        normalized = match.strip().lower()
        if normalized not in seen:
            seen.append(normalized)
    return seen


def safe_attachment_name(value: str, extension: str) -> str:
    value = RESERVED_FILENAME.sub("-", value).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    if not value:
        raise CareerFlowError("Attachment name cannot be empty.")
    suffix = extension.lower()
    if not value.lower().endswith(suffix):
        value += suffix
    if len(value) > 180:
        raise CareerFlowError("Attachment filename is too long.")
    return value


def default_attachment_name(profile: Dict[str, Any], role: str, extension: str) -> str:
    school = ""
    if profile.get("education"):
        school = str(profile["education"][0].get("school", "")).strip()
    parts = [str(profile.get("display_name", "")).strip(), school, role.strip(), "Resume"]
    return safe_attachment_name("-".join(part for part in parts if part), extension)


def markdown_to_email_text(markdown: str) -> str:
    lines = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.lower() in {"# cover letter", "cover letter"}:
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def _select_resume(output: Path) -> Path:
    candidates = [output / "tailored-resume.pdf", output / "tailored-resume.docx", output / "resume.pdf"]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise CareerFlowError("No final resume attachment was found. Build and visually verify the application first.")
    return path


def _validate_attachment(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise CareerFlowError("The resume attachment is missing or empty.")
    if path.suffix.lower() == ".pdf":
        if not path.read_bytes()[:5] == b"%PDF-":
            raise CareerFlowError("The .pdf attachment is not a valid PDF file.")
    elif path.suffix.lower() == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise CareerFlowError("The .docx attachment is not a valid Word file.") from exc
        if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
            raise CareerFlowError("The .docx attachment is missing required Word structures.")
    else:
        raise CareerFlowError("Only PDF and DOCX resume attachments are allowed.")


def _validate_plan(workspace: Workspace, app_dir: Path, plan: Dict[str, Any]) -> None:
    required = {
        "application_id", "from", "to", "subject", "jd_emails_found",
        "attachment_filename", "attachment_relative_path", "attachment_sha256",
        "source_attachment_relative_path", "source_attachment_sha256",
        "body_relative_path", "body_sha256", "application_approval_sha256",
        "build_manifest_sha256",
    }
    if not required.issubset(plan):
        raise CareerFlowError("The email plan is incomplete. Prepare it again.")
    if plan["application_id"] != app_dir.name:
        raise CareerFlowError("The email plan belongs to a different application.")
    if not EMAIL_PATTERN.fullmatch(str(plan["from"])) or not EMAIL_PATTERN.fullmatch(str(plan["to"])):
        raise CareerFlowError("The approved sender or recipient address is invalid.")
    jd_emails = extract_jd_emails(read_text(app_dir / "input" / "jd.md"))
    if plan["jd_emails_found"] != jd_emails:
        raise CareerFlowError("The JD email addresses changed after email preparation.")
    if str(plan["to"]).lower() not in jd_emails:
        raise CareerFlowError("The recipient is not an email address found in the current JD.")
    filename = str(plan["attachment_filename"])
    if Path(filename).name != filename or plan["subject"] != Path(filename).stem:
        raise CareerFlowError("The email subject must exactly match the resume filename without its extension.")
    if any(char in str(plan["subject"]) for char in "\r\n"):
        raise CareerFlowError("The email subject contains an invalid line break.")
    if plan["attachment_relative_path"] != "attachments/%s" % filename:
        raise CareerFlowError("The attachment path does not match the approved resume filename.")
    if plan["body_relative_path"] != "email-body.txt":
        raise CareerFlowError("The email body path is outside the generated delivery package.")
    if plan["source_attachment_relative_path"] not in {
        "output/tailored-resume.pdf", "output/tailored-resume.docx", "output/resume.pdf"
    }:
        raise CareerFlowError("The source attachment is not a supported final resume output.")
    attachment = app_dir / "delivery" / str(plan["attachment_relative_path"])
    _validate_attachment(attachment)


def _email_message(plan: Dict[str, Any], body: str, attachment: Path, add_transport_headers: bool) -> EmailMessage:
    message = EmailMessage()
    message["From"] = plan["from"]
    message["To"] = plan["to"]
    message["Subject"] = plan["subject"]
    if add_transport_headers:
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid(domain=plan["from"].split("@")[-1])
    message.set_content(body)
    subtype = "pdf" if attachment.suffix.lower() == ".pdf" else "vnd.openxmlformats-officedocument.wordprocessingml.document"
    message.add_attachment(attachment.read_bytes(), maintype="application", subtype=subtype, filename=plan["attachment_filename"])
    return message


def prepare_email(
    workspace: Workspace,
    app_id: str,
    recipient: Optional[str] = None,
    sender: Optional[str] = None,
    attachment_name: Optional[str] = None,
) -> Path:
    app_dir = workspace.find_application(app_id)
    meta = workspace.meta(app_dir)
    if meta["stage"] != "built":
        raise CareerFlowError("Email preparation requires a built, unsent application package.")
    delivery = app_dir / "delivery"
    if (delivery / "send-receipt.json").exists() or (delivery / "send-attempt.json").exists():
        raise CareerFlowError("A send or uncertain send attempt already exists. Duplicate sending is blocked.")
    if (delivery / "email-approval.json").exists():
        raise CareerFlowError("The email package is already approved. Create a new application version to revise it.")

    jd_emails = extract_jd_emails(read_text(app_dir / "input" / "jd.md"))
    if not jd_emails:
        raise CareerFlowError("No email address was found in the JD. Sending is blocked; update the JD source first.")
    if recipient:
        to_address = recipient.strip().lower()
        if to_address not in jd_emails:
            raise CareerFlowError("The selected recipient is not one of the email addresses found in the JD.")
    elif len(jd_emails) == 1:
        to_address = jd_emails[0]
    else:
        raise CareerFlowError("Multiple email addresses were found in the JD: %s. Select one with --to." % ", ".join(jd_emails))

    from_address = (sender or os.environ.get("CAREERFLOW_EMAIL_FROM") or os.environ.get("CAREERFLOW_SMTP_USER") or "").strip().lower()
    if not EMAIL_PATTERN.fullmatch(from_address):
        raise CareerFlowError("Set CAREERFLOW_EMAIL_FROM or supply --from with a valid sender address.")

    profile = workspace.profile(meta["user_id"])
    source_attachment = _select_resume(app_dir / "output")
    _validate_attachment(source_attachment)
    filename = safe_attachment_name(attachment_name, source_attachment.suffix) if attachment_name else default_attachment_name(profile, meta["role"], source_attachment.suffix)
    delivery.mkdir(parents=True, exist_ok=True)
    attachment_dir = delivery / "attachments"
    attachment_dir.mkdir(exist_ok=True)
    copied_attachment = attachment_dir / filename
    shutil.copy2(str(source_attachment), str(copied_attachment))
    _validate_attachment(copied_attachment)

    body = markdown_to_email_text(read_text(app_dir / "output" / "cover-letter.md"))
    body_path = delivery / "email-body.txt"
    body_path.write_text(body, encoding="utf-8")
    approval_path = app_dir / "approval.json"
    manifest_path = app_dir / "output" / "manifest.json"
    plan = {
        "schema_version": 2,
        "application_id": app_id,
        "from": from_address,
        "to": to_address,
        "recipient_source": "job_description",
        "jd_emails_found": jd_emails,
        "subject": Path(filename).stem,
        "attachment_filename": filename,
        "attachment_relative_path": "attachments/%s" % filename,
        "attachment_sha256": _sha256(copied_attachment),
        "source_attachment_relative_path": source_attachment.relative_to(app_dir).as_posix(),
        "source_attachment_sha256": _sha256(source_attachment),
        "body_relative_path": "email-body.txt",
        "body_sha256": _sha256(body_path),
        "application_approval_sha256": _sha256(approval_path),
        "build_manifest_sha256": _sha256(manifest_path),
        "prepared_at": utc_now(),
        "status": "prepared",
    }
    plan_path = delivery / "email-plan.json"
    write_json(plan_path, plan)
    _validate_plan(workspace, app_dir, plan)
    preview = _email_message(plan, body, copied_attachment, add_transport_headers=False)
    (delivery / "email-preview.eml").write_bytes(preview.as_bytes())
    write_json(delivery / "status.json", {"status": "prepared", "updated_at": utc_now()})
    return plan_path


def approve_email(workspace: Workspace, app_id: str, confirmed_by: str) -> Path:
    app_dir = workspace.find_application(app_id)
    delivery = app_dir / "delivery"
    plan_path = delivery / "email-plan.json"
    if not plan_path.exists():
        raise CareerFlowError("Prepare the email package before approval.")
    if (delivery / "send-receipt.json").exists() or (delivery / "send-attempt.json").exists():
        raise CareerFlowError("A send attempt already exists; this package cannot be approved again.")
    if not confirmed_by.strip():
        raise CareerFlowError("Approval must identify who confirmed the final email package.")
    plan = load_json(plan_path)
    _validate_plan(workspace, app_dir, plan)
    attachment = delivery / plan["attachment_relative_path"]
    body = delivery / plan["body_relative_path"]
    source_attachment = app_dir / plan["source_attachment_relative_path"]
    checks = {
        "attachment_sha256": _sha256(attachment),
        "body_sha256": _sha256(body),
        "source_attachment_sha256": _sha256(source_attachment),
        "application_approval_sha256": _sha256(app_dir / "approval.json"),
        "build_manifest_sha256": _sha256(app_dir / "output" / "manifest.json"),
    }
    if any(checks[key] != plan[key] for key in checks):
        raise CareerFlowError("The JD, approved application, build, body, or attachment changed after preparation. Prepare again.")
    plan_hash = _sha256(plan_path)
    code_material = "%s|%s|%s|%s" % (plan_hash, plan["to"], plan["subject"], plan["attachment_sha256"])
    confirmation_code = hashlib.sha256(code_material.encode("utf-8")).hexdigest()[:12].upper()
    approval = {
        "confirmed_by": confirmed_by,
        "confirmed_at": utc_now(),
        "plan_sha256": plan_hash,
        "body_sha256": plan["body_sha256"],
        "attachment_sha256": plan["attachment_sha256"],
        "confirmation_code": confirmation_code,
    }
    path = delivery / "email-approval.json"
    write_json(path, approval)
    summary = (
        "FINAL EMAIL REVIEW\n"
        "From: {from_}\nTo: {to}\nSubject: {subject}\nAttachment: {attachment}\n"
        "Attachment SHA-256: {sha}\nConfirmation code: {code}\n\n"
        "Only run email-send after visually checking email-preview.eml and the attachment.\n"
    ).format(from_=plan["from"], to=plan["to"], subject=plan["subject"], attachment=plan["attachment_filename"], sha=plan["attachment_sha256"], code=confirmation_code)
    (delivery / "final-review.txt").write_text(summary, encoding="utf-8")
    write_json(delivery / "status.json", {"status": "approved", "updated_at": utc_now()})
    return path


def send_email(workspace: Workspace, app_id: str, confirmation_code: str, smtp_factory=None, smtp_ssl_factory=None) -> Path:
    app_dir = workspace.find_application(app_id)
    if workspace.meta(app_dir)["stage"] != "built":
        raise CareerFlowError("Email sending is allowed exactly once from the built stage.")
    delivery = app_dir / "delivery"
    receipt_path = delivery / "send-receipt.json"
    attempt_path = delivery / "send-attempt.json"
    if receipt_path.exists() or attempt_path.exists():
        raise CareerFlowError("Duplicate or automatic retry is blocked because a send attempt already exists.")
    plan_path = delivery / "email-plan.json"
    approval_path = delivery / "email-approval.json"
    if not plan_path.exists() or not approval_path.exists():
        raise CareerFlowError("Email plan and explicit approval are required before sending.")
    plan = load_json(plan_path)
    approval = load_json(approval_path)
    if confirmation_code.strip().upper() != approval.get("confirmation_code"):
        raise CareerFlowError("The final confirmation code does not match the approved email package.")
    _validate_plan(workspace, app_dir, plan)
    body_path = delivery / plan["body_relative_path"]
    attachment = delivery / plan["attachment_relative_path"]
    source_attachment = app_dir / plan["source_attachment_relative_path"]
    if approval["plan_sha256"] != _sha256(plan_path):
        raise CareerFlowError("Email plan changed after approval.")
    if approval["body_sha256"] != _sha256(body_path) or approval["attachment_sha256"] != _sha256(attachment):
        raise CareerFlowError("Email body or attachment changed after approval.")
    if plan["source_attachment_sha256"] != _sha256(source_attachment):
        raise CareerFlowError("The built resume changed after email preparation.")
    if plan["application_approval_sha256"] != _sha256(app_dir / "approval.json"):
        raise CareerFlowError("The approved application content changed after email preparation.")
    if plan["build_manifest_sha256"] != _sha256(app_dir / "output" / "manifest.json"):
        raise CareerFlowError("The build manifest changed after email preparation.")

    host = os.environ.get("CAREERFLOW_SMTP_HOST", "").strip()
    user = os.environ.get("CAREERFLOW_SMTP_USER", "").strip()
    password = os.environ.get("CAREERFLOW_SMTP_PASSWORD", "")
    security = os.environ.get("CAREERFLOW_SMTP_SECURITY", "starttls").strip().lower()
    if not host or not user or not password:
        raise CareerFlowError("Set CAREERFLOW_SMTP_HOST, CAREERFLOW_SMTP_USER and CAREERFLOW_SMTP_PASSWORD in the environment.")
    if user.lower() != plan["from"].lower():
        raise CareerFlowError("Configured SMTP user does not match the approved sender address.")
    if security not in {"starttls", "ssl"}:
        raise CareerFlowError("CAREERFLOW_SMTP_SECURITY must be starttls or ssl; unencrypted SMTP is blocked.")
    try:
        port = int(os.environ.get("CAREERFLOW_SMTP_PORT", "465" if security == "ssl" else "587"))
    except ValueError as exc:
        raise CareerFlowError("CAREERFLOW_SMTP_PORT must be an integer.") from exc

    body = body_path.read_text(encoding="utf-8")
    message = _email_message(plan, body, attachment, add_transport_headers=True)
    attempt = {
        "attempt_id": uuid.uuid4().hex,
        "application_id": app_id,
        "started_at": utc_now(),
        "to": plan["to"],
        "subject": plan["subject"],
        "message_id": message["Message-ID"],
        "plan_sha256": approval["plan_sha256"],
        "status": "sending",
    }
    # Persist before contacting SMTP. Any crash after this point becomes an
    # uncertain attempt and must never be retried automatically.
    write_json(attempt_path, attempt)
    smtp_factory = smtp_factory or smtplib.SMTP
    smtp_ssl_factory = smtp_ssl_factory or smtplib.SMTP_SSL
    client = None
    try:
        context = ssl.create_default_context()
        client = smtp_ssl_factory(host, port, timeout=30, context=context) if security == "ssl" else smtp_factory(host, port, timeout=30)
        if security == "starttls":
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        client.login(user, password)
        refused = client.send_message(message)
        if refused:
            raise CareerFlowError("SMTP server did not accept every recipient; status is uncertain and automatic retry is blocked.")
    except Exception as exc:
        attempt.update({"status": "uncertain", "updated_at": utc_now(), "error_type": type(exc).__name__})
        write_json(attempt_path, attempt)
        if isinstance(exc, CareerFlowError):
            raise
        raise CareerFlowError("SMTP delivery did not complete. Status is uncertain; verify the mailbox before any manual action.") from exc
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass

    receipt = {
        "application_id": app_id,
        "attempt_id": attempt["attempt_id"],
        "sent_at": utc_now(),
        "from": plan["from"],
        "to": plan["to"],
        "subject": plan["subject"],
        "attachment_filename": plan["attachment_filename"],
        "attachment_sha256": plan["attachment_sha256"],
        "message_id": message["Message-ID"],
        "smtp_host": host,
        "status": "sent",
    }
    write_json(receipt_path, receipt)
    attempt.update({"status": "sent", "updated_at": utc_now(), "receipt_relative_path": "send-receipt.json"})
    write_json(attempt_path, attempt)
    write_json(delivery / "status.json", {"status": "sent", "updated_at": utc_now()})
    workspace.transition(app_dir, "submitted", {"built"})
    return receipt_path

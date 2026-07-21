# Changelog

## 0.3.0 - 2026-07-21

- Extract a unique HR email address from the stored JD.
- Prepare a reviewable email body, renamed final resume and `.eml` preview.
- Set the subject to the approved attachment filename without its extension.
- Add a dedicated approval hash for recipient, subject, body and attachment.
- Send once through the user's single SMTP account and store a delivery receipt.
- Block ambiguous recipients, changed attachments and duplicate sends.
- Require JD-bound recipient selection, a package-specific confirmation code and encrypted SMTP.
- Persist send intent before contacting SMTP so uncertain outcomes can never be retried automatically.

## 0.2.0 - 2026-07-21

- Package a generalized version of the controlled resume editor.
- Inspect each uploaded PDF or DOCX and generate private per-document parameters.
- Add source-hash, exact-text, line-capacity and approval-plan gates.
- Preserve PDF layout through bounded replacements and outside-region visual diffs.
- Preserve Word package structure through in-place OOXML paragraph replacement.
- Integrate original-format output into the application build command.
- Expand the end-to-end demo and tests to cover the packaged editor.
- Constrain ReportLab to a release range compatible with the supported Python 3.8 runtime.

## 0.1.0 - 2026-07-21

- Initial evidence, application, approval, interview and review workflow.

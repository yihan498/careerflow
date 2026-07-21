# Quality standard

## Resume and cover letter

- Every material claim must map to confirmed profile evidence.
- Preserve organization names, roles, dates and underlying facts.
- Prefer context/object -> personal action -> method/evidence -> result.
- Do not copy a JD line by line or describe transferable methods as direct industry experience.
- Preserve useful numbers; never invent metrics to make a bullet appear stronger.
- Review the complete resume, cover letter and evidence map before approval.

## Interview research

- Current company claims require sources and research dates.
- Prefer official company, regulator, exchange and other primary sources.
- Label inference and unknowns; missing material is not negative evidence.
- Cover business, workflow, role interpretation, resume questions and role questions.

## Email delivery

- Extract recipients from the complete JD. A manual selection is allowed only when choosing among addresses that actually appear in that JD.
- Apply explicit JD filename rules when present; otherwise use the documented default.
- Keep the subject identical to the approved attachment filename without its extension.
- Show recipient, sender, subject, body and attachment before approval.
- Recheck body, plan and attachment hashes immediately before SMTP submission.
- Require the package-specific confirmation code generated after approval.
- Allow encrypted SMTP through STARTTLS or SSL only.
- Write a receipt only after the SMTP server accepts the message. Any send attempt, including an uncertain result, blocks automatic retry until the sender mailbox is checked manually.
- Never store SMTP passwords in files, logs, plans or receipts.

## Review

- Preserve the user's observation before adding interpretation.
- Categorize problems by knowledge, resume evidence, behavior, case/technical, delivery, or process.
- Store each review with its application and update the aggregate summary.
- Convert repeated observations into a future preparation checklist only after they recur.

## Document output

- Verify headings, content and manifests, not only file existence.
- Visually inspect the final PDF for clipping, overlap, missing glyphs and awkward page breaks.
- Never send a build whose approved-content hash no longer matches.
- For an uploaded PDF/DOCX, use the packaged original-format editor and include `document-plan.json` in approval.
- PDF replacements must fit the inspected line capacity and pass searchable-text and outside-region visual-diff checks.
- DOCX replacements must preserve the OOXML package and be rendered in Word or LibreOffice before delivery.

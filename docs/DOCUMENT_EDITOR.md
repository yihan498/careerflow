# Original-format document editor

CareerFlow includes the controlled editor used to write approved resume content back into each user's own PDF or Word file. Agents must use this editor instead of inventing a new file-editing path for every applicant.

## Per-document inspection

The private prototype was stable because it knew one template's exact fields and coordinates. Those values cannot be reused for another resume. CareerFlow now generates a private `document-profile.json` for every uploaded document.

PDF profiles contain page and line region IDs, exact source text, bounding boxes, baselines, font attributes, available width and the source hash. DOCX profiles contain document/header/footer parts, paragraph IDs, exact text, run counts and the source hash.

## Commands

Supplying `.pdf` or `.docx` during onboarding registers the default template automatically:

```powershell
careerflow user-add --profile profile.json --resume original-resume.pdf
```

Register another design when needed:

```powershell
careerflow template-inspect --user candidate-id --source alternate.docx --template-id alternate
```

After drafting, initialize the plan:

```powershell
careerflow template-plan --application example-company-example-intern --template-id default
```

The Agent fills `draft/document-plan.json` using inspected regions:

```json
{
  "template_id": "default",
  "source_sha256": "...",
  "changes": [
    {
      "region_id": "pdf_p001_l0018",
      "old_text": "Exact original line",
      "new_text": "Approved replacement line"
    }
  ]
}
```

The plan joins the approval hash. `careerflow build` invokes the packaged editor automatically.

## PDF guarantees

- Reject changed source hashes, unknown regions, mismatched original text and duplicate changes.
- Calculate replacement width before editing and reject text beyond the original line capacity.
- Redact only approved rectangles and write at the recorded baseline, size and color.
- Confirm replacement text remains searchable.
- Render source/output previews and calculate differences outside approved rectangles.
- Produce final and outside-difference PNG files for mandatory visual review.

Scanned PDFs without searchable text are rejected until an OCR layer is created. The editor does not pretend OCR is layout-safe.

## Word guarantees

- Edit OOXML paragraphs in place instead of rebuilding the resume.
- Preserve package parts, paragraph properties, tables, headers, footers, images and untouched content.
- Validate changed and untouched paragraph text in the output package.
- Produce `tailored-resume.docx` and mark visual QA as required.

Word may reflow when replacement text is longer. Render with Microsoft Word or LibreOffice and inspect pagination, text boxes, tables, fonts and glyphs before delivery.

## Agent boundary

The Agent chooses evidence and prepares the replacement plan. It must not directly manipulate PDF operators, DOCX XML or coordinates. The packaged editor owns source-hash validation, capacity checks, writing and output validation.

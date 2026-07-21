# User onboarding

Every person completes onboarding once. Do not reuse another person's evidence library or template configuration.

## Required inputs

- A complete source resume (`.pdf`, `.docx`, `.md` or `.txt`). PDF/DOCX enables original-format editing.
- A structured UTF-8 profile JSON following `examples/demo/profile.json`.
- Confirmed education, organizations, roles, dates, project actions, metrics, results, and skills.
- For each application, the complete JD rather than only the job title or a short screenshot.
- For online drafting/research, the user's own `OPENAI_API_KEY` supplied through the environment, never a committed file.

## Importing an existing PDF or DOCX

1. Supply the original file to `careerflow user-add --resume`.
2. CareerFlow copies it into the private workspace, hashes it and generates `document-profile.json`.
3. The Agent compares inspected regions with the original and copies confirmed facts into the profile schema.
4. Ask the user to verify names, dates, metrics and claims.
5. Before approval, create and review `document-plan.json`; build invokes the packaged editor.

CareerFlow does not treat text extraction as user confirmation. Text-based PDFs and DOCX files are edited only in registered regions; scanned PDFs stop until OCR is available.

## Initialize

```powershell
$env:CAREERFLOW_HOME = "D:\private-careerflow"
careerflow bootstrap
careerflow user-add --profile path\to\profile.json --resume path\to\source-resume.pdf
```

Use a unique, non-sensitive user ID. The profile itself remains private and is written under `$env:CAREERFLOW_HOME`.

## Per-job workflow

```powershell
careerflow apply --user demo-candidate --company "Northstar Labs" --role "Product Operations Intern" --jd path\to\jd.md
careerflow draft --application northstar-labs-product-operations-intern --provider openai
careerflow template-plan --application northstar-labs-product-operations-intern --template-id default
```

Review these files together:

- `draft/resume.md`
- `draft/cover-letter.md`
- `draft/evidence-map.md`
- `draft/document-plan.json` for PDF/DOCX originals

Only after explicit user approval:

```powershell
careerflow approve --application northstar-labs-product-operations-intern --confirmed-by "user-confirmed"
careerflow build --application northstar-labs-product-operations-intern
```

Open the generated PDF and check clipping, overlap, broken glyphs, spacing and page breaks. HTML is also generated as an editable preview.

When an interview becomes available:

```powershell
careerflow interview --application northstar-labs-product-operations-intern --provider openai
```

After an interview or final outcome:

```powershell
careerflow review --application northstar-labs-product-operations-intern --outcome rejected --notes path\to\notes.md
careerflow status
```

The review remains in that application and is also added to `aggregate/review-summary.md`.

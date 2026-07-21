# Architecture

CareerFlow separates reusable workflow code from private runtime data.

```text
public Git repository                 private runtime workspace
careerflow/                           ~/.careerflow/ (default)
  CLI and state machine                users/<user-id>/
  drafting/research providers            profile/
  templates and approval gate            applications/<application-id>/
  PDF exporter                            aggregate/
  fictional demo and tests
```

## Components

1. **User evidence layer** validates a structured profile and creates a confirmed evidence ledger.
2. **Application layer** creates an isolated directory for each company-role pair and tracks its stage.
3. **Drafting layer** produces a resume, cover letter, and evidence map. `rules` is deterministic and offline; `openai` performs deeper semantic tailoring.
4. **Approval layer** hashes all reviewed drafts. Build fails if content changes afterward.
5. **Output layer** creates Markdown, HTML, a manifest, and optionally PDF.
6. **Interview layer** starts only after the application package is built. Online mode researches current company information; offline mode produces a source ledger and question framework without pretending it performed research.
7. **Review layer** stores job-specific feedback and synchronizes categorized learning to a cross-application summary.

## State machine

```text
created -> drafted -> approved -> built -> interviewing -> closed
             ^          |
             |          +-- content hash must match
             +-- revise before approval
```

The workflow is intentionally gated. A model cannot silently approve its own resume or cover letter.

## Provider boundary

The core has no mandatory cloud dependency. The OpenAI provider calls the Responses API with `store: false`; interview preparation enables the web-search tool. Organizations can replace that adapter without changing the workspace schema or approval state machine.

## Privacy boundary

- Runtime defaults to `~/.careerflow`, outside the clone.
- `.gitignore` excludes common private/runtime locations.
- The release privacy scanner detects common secrets, user paths, email addresses, and phone numbers.
- Public examples use fictional organizations and the reserved `.invalid` email domain.

## PDF boundary

Arbitrary PDFs do not share a reliable editable schema. The reusable system therefore generates a new layout from structured, approved content. Exact edits to a locked personal design require a separate per-user adapter and visual QA; such adapters belong in the private workspace, not this repository.

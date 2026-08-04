# CareerFlow Web Platform Contract

This subtree is isolated from the existing CareerFlow package. Do not modify files outside `web-platform/`.

## Invariants

- Every database and object-storage lookup is scoped by the authenticated `user_id`.
- Agents create review candidates only. They never approve, mutate documents, send email, or advance stages.
- Stage transitions, approval hashes, artifact activation, and review aggregation are deterministic operations.
- Uploaded PDF/DOCX files are parsed only by `document-worker`; the API service must not import PDF/DOCX parsers.
- Provider credentials never enter logs, artifacts, prompts, exception details, or worker requests.
- Model output must pass a shared schema and the existing CareerFlow contracts before it is persisted.
- A failed operation leaves the previous active artifact version untouched.
- External side effects require idempotency keys.

## Required checks

Run from `web-platform/`:

```powershell
python -m pytest tests
npm --prefix frontend test -- --run
npm --prefix frontend run build
docker compose config
powershell -ExecutionPolicy Bypass -File scripts/verify-isolation.ps1
```


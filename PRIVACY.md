# Privacy

CareerFlow is local-first. User profiles, resumes, job descriptions, application outputs, interview notes and review records are written to a separate runtime workspace.

The optional OpenAI provider sends the profile, JD and relevant application content to the configured API for drafting. Interview mode also enables web search. The request sets `store: false`, but users should review their provider's current data controls and organizational policy before enabling it.

Do not commit runtime data or credentials. Run `python scripts/privacy_check.py` before publication. The scanner is a guardrail, not a substitute for reviewing the staged diff.

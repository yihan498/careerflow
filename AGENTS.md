# CareerFlow Agent Contract

本文件是强制执行契约，不是背景说明。开始任务前继续读取 `docs/AGENT_PLAYBOOK.md` 和 `docs/QUALITY_STANDARD.md`。

## SYSTEM_BOUNDARY

```yaml
repository_content: public reusable code only
runtime_default: ~/.careerflow
runtime_must_be_outside_repository: true
one_user_one_evidence_library: true
one_job_one_application_directory: true
personal_data_may_be_committed: false
```

## REQUIRED_INPUTS

```yaml
onboarding:
  - complete source resume
  - structured profile JSON
  - user confirmation of names, dates, metrics and claims
application:
  - existing user_id
  - company name
  - role name
  - complete JD body
interview:
  - application stage is built
  - user explicitly reports an interview or requests preparation
review:
  - application package was built
  - outcome
  - user's first-hand notes
```

If a required source is absent, report the gap. Do not turn missing evidence into a negative fact and do not fabricate a completed output.

## STATE_MACHINE

```text
created -> drafted -> approved -> built -> interviewing -> closed
```

- Do not skip states.
- `drafted` is not approval.
- `approved` requires explicit confirmation of resume, Cover Letter and evidence map.
- Any post-approval draft edit invalidates the approval hash; return to drafting and request confirmation again.
- An application may remain at `built` indefinitely if no interview is received.

## EXECUTION_RULES

1. Treat structured profile facts as the only permitted applicant evidence.
2. Generate resume, Cover Letter and evidence map as one review package.
3. Stop after drafting and present the complete review package to the user.
4. Run `approve` and `build` only after explicit user approval.
5. Start interview research only when the interview condition is met.
6. Separate verified company facts, reasoned inference and unknowns; cite current company-specific claims.
7. Build interview questions from both JD requirements and the approved resume.
8. Preserve the user's first-hand review notes, then classify them; do not replace them with generic coaching language.
9. Keep the job-specific review and aggregate review synchronized.
10. Before public commits, run tests and `python scripts/privacy_check.py`, then inspect the staged diff.

## STOP_CONDITIONS

Stop and request user input when:

- profile facts conflict;
- the JD is incomplete;
- a material resume claim lacks evidence;
- resume or Cover Letter approval is not explicit;
- a proprietary layout must be preserved but no private renderer exists;
- online research is requested without an available provider or network access.

## DONE_DEFINITION

An application stage is complete only when:

- files required by that stage exist;
- state metadata matches the stage;
- claims comply with the evidence boundary;
- approval hash matches before build;
- generated PDF has been visually inspected when PDF is delivered;
- research includes sources or is clearly labeled as an unverified offline framework;
- review is present in both the application and aggregate summary.

## PDF_BOUNDARY

CareerFlow creates a new document from approved structured content. It does not promise lossless editing of arbitrary PDFs. Exact preservation of a proprietary layout requires a user-specific adapter stored outside the public repository. Always inspect the rendered PDF visually.

## NEVER_COMMIT

- real resumes, names, personal email addresses or phone numbers;
- real application folders, interview notes or personal evidence libraries;
- `.env`, API keys, access tokens or credentials;
- absolute paths identifying a real user;
- data or code copied from another private career workspace.

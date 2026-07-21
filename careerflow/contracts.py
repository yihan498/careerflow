from __future__ import annotations

import re
from typing import Dict


CONTRACT_VERSION = "1.0"

DRAFT_FILES = {"resume.md", "cover-letter.md", "evidence-map.md"}
RESUME_SECTIONS = ["## Target", "## Education", "## Relevant Experience", "## Skills"]
INTERVIEW_SECTIONS = [
    "## 1. Evidence Boundary and Research Date",
    "## 2. Company Overview",
    "## 3. Relevant Business Workflow",
    "## 4. JD Decomposition",
    "## 5. Resume-to-Role Map",
    "## 6. Company and Role Questions",
    "## 7. Resume Follow-ups",
    "## 8. Mock Interview and Final Checklist",
    "## 9. Source Ledger",
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_draft_bundle(drafts: Dict[str, str]) -> None:
    """Validate structure only; factual correctness remains a human approval gate."""
    _require(set(drafts) == DRAFT_FILES, "Draft bundle must contain exactly the three contracted files.")
    for name, content in drafts.items():
        _require(isinstance(content, str) and len(content.strip()) >= 40, "%s is empty or too short." % name)
        _require(len(content) <= 50000, "%s exceeds the contracted size limit." % name)
        _require("```json" not in content.lower(), "%s contains an unparsed JSON wrapper." % name)
        _require("TODO" not in content, "%s contains an unresolved TODO placeholder." % name)
    _require(drafts["resume.md"].lstrip().startswith("# "), "Resume must start with one Markdown title.")
    resume_positions = []
    for heading in RESUME_SECTIONS:
        _require(drafts["resume.md"].count(heading) == 1, "Resume must contain exactly one '%s' section." % heading)
        resume_positions.append(drafts["resume.md"].index(heading))
    _require(resume_positions == sorted(resume_positions), "Resume sections are out of contract order.")
    _require(drafts["cover-letter.md"].lstrip().startswith("# Cover Letter"), "Cover letter must use the contracted title.")
    evidence = drafts["evidence-map.md"]
    _require(evidence.lstrip().startswith("# Evidence Map"), "Evidence map must use the contracted title.")
    _require(evidence.count("## Claim Mapping") == 1, "Evidence map must contain exactly one Claim Mapping section.")
    _require(evidence.count("## JD Gaps") == 1, "Evidence map must contain exactly one JD Gaps section.")
    _require(evidence.index("## Claim Mapping") < evidence.index("## JD Gaps"), "Evidence map sections are out of contract order.")


def validate_interview_brief(brief: str, require_sources: bool) -> None:
    """Require a stable brief skeleton while leaving analysis inside sections to the agent."""
    positions = []
    for heading in INTERVIEW_SECTIONS:
        _require(brief.count(heading) == 1, "Interview brief must contain exactly one '%s' section." % heading)
        positions.append(brief.index(heading))
    _require(positions == sorted(positions), "Interview brief sections are out of contract order.")
    if require_sources:
        source_ledger = brief[brief.index("## 9. Source Ledger"):]
        _require(re.search(r"https?://[^\s)>]+", source_ledger) is not None, "Online interview source ledger must include source URLs.")
        _require("TODO" not in brief, "Online interview research cannot contain TODO placeholders.")
        _require(
            any(label in brief for label in ("[Verified]", "[Inference]", "[Unknown]")),
            "Online interview findings must label their evidence status.",
        )

import pytest

from shared.contracts import Stage, canonical_hash, require_transition
from shared.careerflow_compat import validate_interview_brief


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_state_machine_blocks_skipping_approval():
    with pytest.raises(ValueError):
        require_transition(Stage.DRAFTED, Stage.BUILT)


def test_explicit_interview_transition_is_allowed():
    require_transition(Stage.BUILT, Stage.INTERVIEWING)
    require_transition(Stage.SUBMITTED, Stage.INTERVIEWING)


def test_interview_verified_claims_must_use_retrieved_evidence_ids():
    headings = [
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
    valid = "\ncontent [Verified:SRC-01]\n".join(headings) + "\nhttps://example.com"
    validate_interview_brief(valid, True, {"SRC-01"})
    with pytest.raises(ValueError):
        validate_interview_brief(valid.replace("SRC-01", "SRC-99"), True, {"SRC-01"})
    with pytest.raises(ValueError):
        validate_interview_brief(valid.replace("[Verified:SRC-01]", "[Verified]"), True, {"SRC-01"})

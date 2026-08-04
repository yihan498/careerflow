import pytest

from shared.contracts import Stage, canonical_hash, require_transition


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_state_machine_blocks_skipping_approval():
    with pytest.raises(ValueError):
        require_transition(Stage.DRAFTED, Stage.BUILT)


def test_explicit_interview_transition_is_allowed():
    require_transition(Stage.BUILT, Stage.INTERVIEWING)
    require_transition(Stage.SUBMITTED, Stage.INTERVIEWING)


import pytest

from undm.domain.lifecycle import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    TRANSIENT_STATES,
    InvalidTransitionError,
    interrupted_outcome,
    transition,
)
from undm.domain.lifecycle import (
    DeploymentState as S,
)


def walk(path):
    state = path[0]
    for nxt in path[1:]:
        state = transition(state, nxt)
    return state


def test_live_path_is_legal():
    assert walk([S.DRAFT, S.VALIDATING, S.AWAITING_APPROVAL, S.READY, S.PREFLIGHT,
                 S.BACKING_UP, S.DEPLOYING, S.VERIFYING, S.SUCCEEDED]) is S.SUCCEEDED


def test_dry_run_path_is_legal():
    assert walk([S.DRAFT, S.VALIDATING, S.READY, S.PREFLIGHT, S.SUCCEEDED]) is S.SUCCEEDED


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
def test_terminal_states_have_no_exits(terminal):
    assert not ALLOWED_TRANSITIONS.get(terminal)


@pytest.mark.parametrize("bad", [
    (S.AWAITING_APPROVAL, S.PREFLIGHT),  # skipping approval
    (S.READY, S.DEPLOYING),              # skipping preflight and backup
    (S.PREFLIGHT, S.DEPLOYING),          # skipping backup
    (S.DEPLOYING, S.SUCCEEDED),          # skipping verification
])
def test_safety_gates_cannot_be_skipped(bad):
    with pytest.raises(InvalidTransitionError):
        transition(*bad)


def test_interrupted_outcomes():
    assert interrupted_outcome(S.DEPLOYING) is S.RECOVERY_REQUIRED
    assert interrupted_outcome(S.VERIFYING) is S.RECOVERY_REQUIRED
    assert interrupted_outcome(S.RECOVERING) is S.RECOVERY_REQUIRED
    assert interrupted_outcome(S.PREFLIGHT) is S.FAILED
    assert interrupted_outcome(S.READY) is None
    assert all(interrupted_outcome(s) is not None for s in TRANSIENT_STATES)

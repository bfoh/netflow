"""Deployment lifecycle state machine.

Stages (directive 4.4): Draft -> Validate -> Preview -> Approve -> Preflight ->
Execute -> Verify -> Complete or Recover. State names follow directive 15.

    DRAFT -> VALIDATING -> AWAITING_APPROVAL -> READY -> PREFLIGHT -> BACKING_UP
          -> DEPLOYING -> VERIFYING -> SUCCEEDED
    (dry runs: VALIDATING -> READY, and PREFLIGHT -> SUCCEEDED; nothing is changed)

    FAILED            stopped before any device was changed
    RECOVERING        restoring devices after a failure (transient; UNDM addition)
    ROLLED_BACK       every changed device was automatically restored
    RECOVERY_REQUIRED at least one device needs manual attention, or the
                      application stopped while devices were being changed
    CANCELLED         withdrawn before execution

Transient states are persisted as they are entered so that an interrupted
process can be detected on restart (see ``interrupted_outcome``).
"""

from enum import StrEnum


class DeploymentState(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    PREFLIGHT = "preflight"
    BACKING_UP = "backing_up"
    DEPLOYING = "deploying"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    RECOVERY_REQUIRED = "recovery_required"
    CANCELLED = "cancelled"


_S = DeploymentState

TERMINAL_STATES = frozenset(
    {_S.SUCCEEDED, _S.FAILED, _S.ROLLED_BACK, _S.RECOVERY_REQUIRED, _S.CANCELLED}
)
# States that only exist while work is in progress.
TRANSIENT_STATES = frozenset(
    {_S.VALIDATING, _S.PREFLIGHT, _S.BACKING_UP, _S.DEPLOYING, _S.VERIFYING, _S.RECOVERING}
)
# Transient states during which devices may already have been changed.
DEVICE_CHANGING_STATES = frozenset({_S.DEPLOYING, _S.VERIFYING, _S.RECOVERING})

ALLOWED_TRANSITIONS: dict[DeploymentState, frozenset[DeploymentState]] = {
    _S.DRAFT: frozenset({_S.VALIDATING, _S.CANCELLED}),
    _S.VALIDATING: frozenset({_S.AWAITING_APPROVAL, _S.READY, _S.FAILED}),
    _S.AWAITING_APPROVAL: frozenset({_S.READY, _S.CANCELLED}),
    _S.READY: frozenset({_S.PREFLIGHT, _S.CANCELLED}),
    _S.PREFLIGHT: frozenset({_S.BACKING_UP, _S.SUCCEEDED, _S.FAILED}),
    _S.BACKING_UP: frozenset({_S.DEPLOYING, _S.FAILED}),
    _S.DEPLOYING: frozenset({_S.VERIFYING, _S.RECOVERING, _S.RECOVERY_REQUIRED}),
    _S.VERIFYING: frozenset({_S.SUCCEEDED, _S.RECOVERING, _S.RECOVERY_REQUIRED}),
    _S.RECOVERING: frozenset({_S.ROLLED_BACK, _S.RECOVERY_REQUIRED}),
}


class InvalidTransitionError(ValueError):
    def __init__(self, current: DeploymentState, target: DeploymentState) -> None:
        super().__init__(f"Illegal deployment transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: DeploymentState, target: DeploymentState) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def transition(current: DeploymentState, target: DeploymentState) -> DeploymentState:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target


def interrupted_outcome(state: DeploymentState) -> DeploymentState | None:
    """Terminal state for a deployment found in ``state`` after a process restart.

    Returns None when the state is not transient (nothing was in progress).
    """
    if state in DEVICE_CHANGING_STATES:
        return _S.RECOVERY_REQUIRED
    if state in TRANSIENT_STATES:
        return _S.FAILED
    return None

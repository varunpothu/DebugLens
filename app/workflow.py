"""Small, auditable state machine for the debugging lifecycle.

This module records state transitions only. It does not run code, access browsers, or apply patches.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class WorkflowState(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    EVIDENCE_COLLECTED = "evidence_collected"
    HYPOTHESES_READY = "hypotheses_ready"
    HUMAN_REVIEW = "human_review"
    REPRODUCED = "reproduced"
    PATCH_PROPOSED = "patch_proposed"
    TESTED = "tested"
    VERIFIED = "verified"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = {WorkflowState.VERIFIED, WorkflowState.REJECTED, WorkflowState.FAILED, WorkflowState.CANCELLED}
ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.RECEIVED: {WorkflowState.VALIDATED, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.VALIDATED: {WorkflowState.EVIDENCE_COLLECTED, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.EVIDENCE_COLLECTED: {WorkflowState.HYPOTHESES_READY, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.HYPOTHESES_READY: {WorkflowState.HUMAN_REVIEW, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.HUMAN_REVIEW: {WorkflowState.REPRODUCED, WorkflowState.REJECTED, WorkflowState.CANCELLED},
    WorkflowState.REPRODUCED: {WorkflowState.PATCH_PROPOSED, WorkflowState.REJECTED, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.PATCH_PROPOSED: {WorkflowState.TESTED, WorkflowState.REJECTED, WorkflowState.FAILED, WorkflowState.CANCELLED},
    WorkflowState.TESTED: {WorkflowState.VERIFIED, WorkflowState.PATCH_PROPOSED, WorkflowState.REJECTED, WorkflowState.FAILED, WorkflowState.CANCELLED},
}


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    workflow_id: str
    from_state: WorkflowState | None
    to_state: WorkflowState
    actor: str
    reason: str
    timestamp: datetime


@dataclass(slots=True)
class DebugWorkflow:
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    state: WorkflowState = WorkflowState.RECEIVED
    events: list[AuditEvent] = field(default_factory=list)

    def transition(self, target: WorkflowState, *, actor: str, reason: str) -> AuditEvent:
        if not actor.strip() or not reason.strip():
            raise ValueError("Every transition requires a non-empty actor and reason.")
        if self.state in TERMINAL_STATES:
            raise ValueError(f"Workflow is terminal ({self.state}) and cannot transition.")
        if target not in ALLOWED_TRANSITIONS.get(self.state, set()):
            raise ValueError(f"Illegal workflow transition: {self.state} -> {target}.")
        previous = self.state
        self.state = target
        event = AuditEvent(
            event_id=str(uuid4()),
            workflow_id=self.workflow_id,
            from_state=previous,
            to_state=target,
            actor=actor,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
        self.events.append(event)
        return event

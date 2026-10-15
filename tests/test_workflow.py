import pytest

from app.workflow import DebugWorkflow, WorkflowState


def test_workflow_records_valid_transition() -> None:
    workflow = DebugWorkflow()
    event = workflow.transition(WorkflowState.VALIDATED, actor="api", reason="Image validated")
    assert workflow.state is WorkflowState.VALIDATED
    assert event.from_state is WorkflowState.RECEIVED
    assert event.to_state is WorkflowState.VALIDATED
    assert event.workflow_id == workflow.workflow_id


def test_workflow_rejects_skipped_states() -> None:
    workflow = DebugWorkflow()
    with pytest.raises(ValueError, match="Illegal workflow transition"):
        workflow.transition(WorkflowState.VERIFIED, actor="system", reason="Skip review")


def test_workflow_requires_actor_and_reason() -> None:
    workflow = DebugWorkflow()
    with pytest.raises(ValueError, match="actor and reason"):
        workflow.transition(WorkflowState.VALIDATED, actor="", reason="")


def test_terminal_workflow_cannot_continue() -> None:
    workflow = DebugWorkflow()
    workflow.transition(WorkflowState.FAILED, actor="worker", reason="Provider unavailable")
    with pytest.raises(ValueError, match="terminal"):
        workflow.transition(WorkflowState.VALIDATED, actor="worker", reason="Retry")

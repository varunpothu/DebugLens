import pytest

from app.config import get_settings
from app.run_store import create_run, get_run, initialise_store, list_runs, transition_run
from app.workflow import WorkflowState


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "debuglens-test.db"))
    get_settings.cache_clear()
    initialise_store()
    yield
    get_settings.cache_clear()


def sample_analysis() -> dict[str, object]:
    return {
        "analysis_id": "analysis-test",
        "provider": "mock",
        "provider_version": "baseline-1",
        "findings": [],
        "test_plan": ["Reproduce"],
        "limitations": ["Mock mode does not inspect pixels."],
    }


def test_create_run_persists_analysis_and_audit_history() -> None:
    run = create_run(
        bug_report="The modal is clipped",
        screenshot_sha256="a" * 64,
        analysis=sample_analysis(),
    )
    assert run["state"] == WorkflowState.HUMAN_REVIEW.value
    assert run["analysis"]["analysis_id"] == "analysis-test"
    assert len(run["events"]) == 4
    assert get_run(run["workflow_id"])["screenshot_sha256"] == "a" * 64


def test_list_runs_returns_newest_first_and_respects_limit() -> None:
    first = create_run(bug_report="first", screenshot_sha256="a" * 64, analysis=sample_analysis())
    second = create_run(bug_report="second", screenshot_sha256="b" * 64, analysis=sample_analysis())
    result = list_runs(limit=1)
    assert len(result) == 1
    assert result[0]["workflow_id"] == second["workflow_id"]
    assert first["workflow_id"] != second["workflow_id"]


def test_transition_requires_legal_state_and_audit_reason() -> None:
    run = create_run(bug_report=None, screenshot_sha256="a" * 64, analysis=sample_analysis())
    with pytest.raises(ValueError, match="Illegal workflow transition"):
        transition_run(
            run["workflow_id"],
            target=WorkflowState.VERIFIED,
            actor="reviewer",
            reason="Trying to skip required checks",
        )
    updated = transition_run(
        run["workflow_id"],
        target=WorkflowState.REPRODUCED,
        actor="reviewer",
        reason="Reproduced on a local test page",
    )
    assert updated["state"] == WorkflowState.REPRODUCED.value
    assert updated["events"][-1]["actor"] == "reviewer"
    assert updated["human_review_required"] is True


def test_missing_run_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_run("not-found")

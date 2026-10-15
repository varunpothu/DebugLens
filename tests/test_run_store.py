from hashlib import sha256

import pytest

from app.config import get_settings
from app.run_store import (
    attach_browser_evidence,
    create_patch_proposal,
    create_run,
    get_run,
    initialise_store,
    list_runs,
    record_test_result,
    transition_run,
)
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
            target=WorkflowState.RECEIVED,
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


def test_browser_evidence_is_persisted_without_raw_screenshot() -> None:
    run = create_run(bug_report="Button misaligned", screenshot_sha256="a" * 64, analysis=sample_analysis())
    updated = attach_browser_evidence(
        run["workflow_id"],
        actor="reviewer",
        evidence={"final_url": "https://demo.example.org/", "raw_screenshot_retained": False},
    )
    assert updated["browser_evidence"]["raw_screenshot_retained"] is False
    assert updated["events"][-1]["event_type"] == "browser_evidence_attached"
    assert updated["events"][-1]["actor"] == "reviewer"


def test_missing_run_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_run("not-found")



def test_patch_proposal_and_test_result_gate_verification() -> None:
    run = create_run(bug_report="Button overflows", screenshot_sha256="a" * 64, analysis=sample_analysis())
    run = transition_run(
        run["workflow_id"],
        target=WorkflowState.REPRODUCED,
        actor="reviewer",
        reason="Reproduced in the local fixture at 390x844.",
    )
    diff = "--- a/app.css\n+++ b/app.css\n@@\n-.button { width: 120%; }\n+.button { max-width: 100%; }\n"
    run = create_patch_proposal(
        run["workflow_id"],
        patch_diff=diff,
        rationale="Constrain the button to its parent container.",
        risk="low",
        rollback_plan="Revert the one-file CSS diff.",
        actor="reviewer",
    )
    digest = sha256(diff.encode("utf-8")).hexdigest()
    assert run["state"] == WorkflowState.PATCH_PROPOSED.value
    assert run["patch_proposal"]["patch_sha256"] == digest

    with pytest.raises(ValueError, match="current patch SHA-256"):
        record_test_result(
            run["workflow_id"],
            patch_sha256="0" * 64,
            outcome="passed",
            command="pytest -q",
            summary="All tests passed",
            actor="reviewer",
        )

    run = record_test_result(
        run["workflow_id"],
        patch_sha256=digest,
        outcome="passed",
        command="pytest -q",
        summary="Ran locally; regression test passed.",
        actor="reviewer",
    )
    assert run["state"] == WorkflowState.TESTED.value
    run = transition_run(
        run["workflow_id"],
        target=WorkflowState.VERIFIED,
        actor="reviewer",
        reason="Reviewed the diff and test output; accepted for this test fixture.",
    )
    assert run["state"] == WorkflowState.VERIFIED.value
    assert run["test_reports"][0]["outcome"] == "passed"


def test_cannot_propose_patch_before_reproduction() -> None:
    run = create_run(bug_report="Issue", screenshot_sha256="a" * 64, analysis=sample_analysis())
    with pytest.raises(ValueError, match="only allowed after"):
        create_patch_proposal(
            run["workflow_id"],
            patch_diff="diff --git a/a b/a",
            rationale="Test",
            risk="low",
            rollback_plan="Revert",
            actor="reviewer",
        )


def test_cannot_mark_verified_without_patch_and_passing_test() -> None:
    run = create_run(bug_report="Issue", screenshot_sha256="a" * 64, analysis=sample_analysis())
    with pytest.raises(ValueError, match="Verification requires a proposed patch"):
        transition_run(
            run["workflow_id"],
            target=WorkflowState.VERIFIED,
            actor="reviewer",
            reason="Skip required checks",
        )


def test_failed_test_can_be_followed_by_a_revised_patch() -> None:
    run = create_run(bug_report="Issue", screenshot_sha256="a" * 64, analysis=sample_analysis())
    run = transition_run(
        run["workflow_id"],
        target=WorkflowState.REPRODUCED,
        actor="reviewer",
        reason="Reproduced on local test page.",
    )
    first_diff = "diff --git a/a.css b/a.css\n-old\n+bad"
    run = create_patch_proposal(
        run["workflow_id"],
        patch_diff=first_diff,
        rationale="First attempt",
        risk="low",
        rollback_plan="Revert the diff",
        actor="reviewer",
    )
    first_digest = sha256(first_diff.encode("utf-8")).hexdigest()
    run = record_test_result(
        run["workflow_id"],
        patch_sha256=first_digest,
        outcome="failed",
        command="pytest -q",
        summary="Regression test still fails.",
        actor="reviewer",
    )
    revised_diff = "diff --git a/a.css b/a.css\n-old\n+fixed"
    run = create_patch_proposal(
        run["workflow_id"],
        patch_diff=revised_diff,
        rationale="Adjust the selector based on test failure.",
        risk="low",
        rollback_plan="Revert the revised diff",
        actor="reviewer",
    )
    assert run["state"] == WorkflowState.PATCH_PROPOSED.value
    assert run["patch_proposal"]["patch_sha256"] == sha256(revised_diff.encode("utf-8")).hexdigest()

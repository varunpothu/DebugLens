"""Small SQLite repository for durable local debugging runs and audit events.

Use a managed database and tenant-scoped authorisation before multi-user deployment.
"""
from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from app.config import get_settings
from app.workflow import DebugWorkflow, TERMINAL_STATES, WorkflowState


def _database_path() -> Path:
    return Path(get_settings().database_path).expanduser()


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_store() -> None:
    with _connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS debug_runs (
                workflow_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state TEXT NOT NULL,
                bug_report TEXT,
                screenshot_sha256 TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                browser_evidence_json TEXT,
                events_json TEXT NOT NULL
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_debug_runs_updated ON debug_runs(updated_at DESC)")
        db.execute(
            """CREATE TABLE IF NOT EXISTS patch_proposals (
                proposal_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                patch_sha256 TEXT NOT NULL,
                patch_diff TEXT NOT NULL,
                rationale TEXT NOT NULL,
                risk TEXT NOT NULL,
                rollback_plan TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_patch_proposals_run ON patch_proposals(workflow_id, created_at DESC)")
        db.execute(
            """CREATE TABLE IF NOT EXISTS test_reports (
                report_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                patch_sha256 TEXT NOT NULL,
                outcome TEXT NOT NULL,
                command TEXT NOT NULL,
                summary TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_test_reports_run ON test_reports(workflow_id, created_at DESC)")
        db.execute(
            """CREATE TABLE IF NOT EXISTS execution_reports (
                report_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                patch_sha256 TEXT NOT NULL,
                suite TEXT NOT NULL,
                outcome TEXT NOT NULL,
                exit_code INTEGER,
                timed_out INTEGER NOT NULL,
                duration_seconds REAL NOT NULL,
                workspace_sha256 TEXT NOT NULL,
                output TEXT NOT NULL,
                output_truncated INTEGER NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_execution_reports_run ON execution_reports(workflow_id, created_at DESC)")


def _event_dict(event: Any) -> dict[str, Any]:
    return {
        "event_type": "state_transition",
        "event_id": event.event_id,
        "workflow_id": event.workflow_id,
        "from_state": event.from_state.value if event.from_state else None,
        "to_state": event.to_state.value,
        "actor": event.actor,
        "reason": event.reason,
        "timestamp": event.timestamp.isoformat(),
    }


def create_run(
    *,
    bug_report: str | None,
    screenshot_sha256: str,
    analysis: dict[str, Any],
    browser_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    initialise_store()
    workflow = DebugWorkflow()
    now = datetime.now(timezone.utc).isoformat()
    workflow.transition(WorkflowState.VALIDATED, actor="system", reason="Screenshot passed upload and decode validation.")
    workflow.transition(
        WorkflowState.EVIDENCE_COLLECTED,
        actor="system",
        reason="Screenshot metadata and analysis evidence were recorded.",
    )
    workflow.transition(
        WorkflowState.HYPOTHESES_READY,
        actor="analysis_service",
        reason="Structured findings and recommended checks were generated.",
    )
    workflow.transition(
        WorkflowState.HUMAN_REVIEW,
        actor="system",
        reason="Human review is required before reproduction or code changes.",
    )
    events = [_event_dict(event) for event in workflow.events]
    with _connect() as db:
        db.execute(
            """INSERT INTO debug_runs
            (workflow_id, created_at, updated_at, state, bug_report, screenshot_sha256,
             analysis_json, browser_evidence_json, events_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow.workflow_id,
                now,
                now,
                workflow.state.value,
                bug_report,
                screenshot_sha256,
                json.dumps(analysis, separators=(",", ":")),
                json.dumps(browser_evidence, separators=(",", ":")) if browser_evidence else None,
                json.dumps(events, separators=(",", ":")),
            ),
        )
    return get_run(workflow.workflow_id)


def get_run(workflow_id: str) -> dict[str, Any]:
    initialise_store()
    with _connect() as db:
        row = db.execute("SELECT * FROM debug_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        proposal = db.execute(
            "SELECT * FROM patch_proposals WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 1",
            (workflow_id,),
        ).fetchone()
        reports = db.execute(
            "SELECT report_id, patch_sha256, outcome, command, summary, actor, created_at "
            "FROM test_reports WHERE workflow_id = ? ORDER BY created_at DESC",
            (workflow_id,),
        ).fetchall()
        execution_reports = db.execute(
            "SELECT report_id, patch_sha256, suite, outcome, exit_code, timed_out, duration_seconds, "
            "workspace_sha256, output, output_truncated, actor, created_at "
            "FROM execution_reports WHERE workflow_id = ? ORDER BY created_at DESC",
            (workflow_id,),
        ).fetchall()
    if row is None:
        raise KeyError(workflow_id)
    result = _decode_row(row)
    result["patch_proposal"] = dict(proposal) if proposal is not None else None
    result["test_reports"] = [dict(report) for report in reports]
    result["execution_reports"] = [
        {**dict(report), "timed_out": bool(report["timed_out"]), "output_truncated": bool(report["output_truncated"])}
        for report in execution_reports
    ]
    return result


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    initialise_store()
    safe_limit = max(1, min(limit, 100))
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM debug_runs ORDER BY updated_at DESC LIMIT ?", (safe_limit,)
        ).fetchall()
    return [_decode_row(row) for row in rows]


def transition_run(
    workflow_id: str, *, target: WorkflowState, actor: str, reason: str
) -> dict[str, Any]:
    initialise_store()
    if not actor.strip() or len(actor) > 120:
        raise ValueError("Actor must contain 1 to 120 characters.")
    if not reason.strip() or len(reason) > 1000:
        raise ValueError("Reason must contain 1 to 1000 characters.")
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM debug_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(workflow_id)
        record = _decode_row(row)
        events = record["events"]
        current = WorkflowState(record["state"])
        if target in {WorkflowState.PATCH_PROPOSED, WorkflowState.TESTED}:
            db.rollback()
            raise ValueError("Use the dedicated patch proposal or test result endpoint for this transition.")
        if target == WorkflowState.VERIFIED:
            patch = db.execute(
                "SELECT patch_sha256 FROM patch_proposals WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 1",
                (workflow_id,),
            ).fetchone()
            report = db.execute(
                "SELECT report_id, patch_sha256, suite, outcome, exit_code, timed_out, workspace_sha256 "
                "FROM execution_reports WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 1",
                (workflow_id,),
            ).fetchone()
            if current != WorkflowState.TESTED or patch is None or report is None:
                db.rollback()
                raise ValueError("Verification requires a proposed patch and a trusted execution report.")
            if (
                report["outcome"] != "passed"
                or report["exit_code"] != 0
                or bool(report["timed_out"])
                or report["patch_sha256"] != patch["patch_sha256"]
            ):
                db.rollback()
                raise ValueError("Verification requires a passing execution report for the current patch digest.")
        workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
        try:
            event = workflow.transition(target, actor=actor, reason=reason)
        except ValueError:
            db.rollback()
            raise
        events.append(_event_dict(event))
        now = datetime.now(timezone.utc).isoformat()
        if target == WorkflowState.VERIFIED:
            # Persist the exact patch and trusted execution report that satisfied the gate.
            # This is an audit record, not a substitute for production user identity/RBAC.
            events.append({
                "event_type": "verification_approval_recorded",
                "event_id": str(uuid4()),
                "workflow_id": workflow_id,
                "from_state": current.value,
                "to_state": target.value,
                "actor": actor,
                "reason": reason,
                "timestamp": now,
                "patch_sha256": patch["patch_sha256"],
                "execution_report_id": report["report_id"],
                "execution_suite": report["suite"],
                "workspace_sha256": report["workspace_sha256"],
            })
        db.execute(
            "UPDATE debug_runs SET state = ?, updated_at = ?, events_json = ? WHERE workflow_id = ?",
            (target.value, now, json.dumps(events, separators=(",", ":")), workflow_id),
        )
        db.commit()
    return get_run(workflow_id)



def attach_browser_evidence(
    workflow_id: str,
    *,
    actor: str,
    evidence: dict[str, Any],
    investigation_pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach minimised browser evidence and record who initiated the capture."""
    initialise_store()
    if not actor.strip() or len(actor) > 120:
        raise ValueError("Actor must contain 1 to 120 characters.")
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM debug_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(workflow_id)
        record = _decode_row(row)
        events = record["events"]
        analysis = record["analysis"]
        if investigation_pipeline is not None:
            analysis["investigation_pipeline"] = investigation_pipeline
        now = datetime.now(timezone.utc).isoformat()
        events.append({
            "event_type": "browser_evidence_attached",
            "event_id": str(uuid4()),
            "workflow_id": workflow_id,
            "from_state": record["state"],
            "to_state": record["state"],
            "actor": actor,
            "reason": "Approved browser capture completed; metadata and analysis were attached.",
            "timestamp": now,
        })
        db.execute(
            """UPDATE debug_runs SET browser_evidence_json = ?, analysis_json = ?, updated_at = ?, events_json = ?
               WHERE workflow_id = ?""",
            (
                json.dumps(evidence, separators=(",", ":")),
                json.dumps(analysis, separators=(",", ":")),
                now,
                json.dumps(events, separators=(",", ":")),
                workflow_id,
            ),
        )
        db.commit()
    return get_run(workflow_id)


def create_patch_proposal(
    workflow_id: str,
    *,
    patch_diff: str,
    rationale: str,
    risk: str,
    rollback_plan: str,
    actor: str,
) -> dict[str, Any]:
    """Store a human-authored diff and transition a reproduced run to patch proposed."""
    initialise_store()
    if not patch_diff.strip() or len(patch_diff) > 200_000:
        raise ValueError("Patch diff must contain 1 to 200000 characters.")
    if not actor.strip() or len(actor) > 120:
        raise ValueError("Actor must contain 1 to 120 characters.")
    patch_digest = sha256(patch_diff.encode("utf-8")).hexdigest()
    proposal_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM debug_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(workflow_id)
        record = _decode_row(row)
        current = WorkflowState(record["state"])
        if current not in {WorkflowState.REPRODUCED, WorkflowState.PATCH_PROPOSED}:
            db.rollback()
            raise ValueError("A patch proposal is only allowed after reproduction or during patch revision.")
        events = record["events"]
        if current == WorkflowState.REPRODUCED:
            workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
            event = workflow.transition(
                WorkflowState.PATCH_PROPOSED,
                actor=actor,
                reason=f"Patch proposal {patch_digest} created for human review.",
            )
            events.append(_event_dict(event))
            next_state = WorkflowState.PATCH_PROPOSED
        else:
            next_state = current
        events.append({
            "event_type": "patch_proposal_created",
            "event_id": proposal_id,
            "workflow_id": workflow_id,
            "from_state": current.value,
            "to_state": WorkflowState.PATCH_PROPOSED.value,
            "actor": actor,
            "reason": rationale[:1000],
            "timestamp": now,
            "patch_sha256": patch_digest,
        })
        db.execute(
            """INSERT INTO patch_proposals
            (proposal_id, workflow_id, patch_sha256, patch_diff, rationale, risk, rollback_plan, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (proposal_id, workflow_id, patch_digest, patch_diff, rationale, risk, rollback_plan, actor, now),
        )
        db.execute(
            "UPDATE debug_runs SET state = ?, updated_at = ?, events_json = ? WHERE workflow_id = ?",
            (next_state.value, now, json.dumps(events, separators=(",", ":")), workflow_id),
        )
        db.commit()
    return get_run(workflow_id)


def record_test_result(
    workflow_id: str,
    *,
    patch_sha256: str,
    outcome: str,
    command: str,
    summary: str,
    actor: str,
) -> dict[str, Any]:
    """Record a reviewer-reported test outcome bound to the exact patch digest."""
    initialise_store()
    if outcome not in {"passed", "failed"}:
        raise ValueError("Test outcome must be passed or failed.")
    if not actor.strip() or len(actor) > 120:
        raise ValueError("Actor must contain 1 to 120 characters.")
    report_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM debug_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(workflow_id)
        record = _decode_row(row)
        current = WorkflowState(record["state"])
        patch = db.execute(
            "SELECT patch_sha256 FROM patch_proposals WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 1",
            (workflow_id,),
        ).fetchone()
        if current not in {WorkflowState.PATCH_PROPOSED, WorkflowState.TESTED}:
            db.rollback()
            raise ValueError("Test results can only be recorded for a proposed patch.")
        if patch is None or patch["patch_sha256"] != patch_sha256:
            db.rollback()
            raise ValueError("Test result must reference the current patch SHA-256 digest.")
        events = record["events"]
        if outcome == "passed" and current == WorkflowState.PATCH_PROPOSED:
            workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
            event = workflow.transition(
                WorkflowState.TESTED,
                actor=actor,
                reason=f"Reviewer reported tests passed for patch {patch_sha256}.",
            )
            events.append(_event_dict(event))
            next_state = WorkflowState.TESTED
        elif outcome == "failed" and current == WorkflowState.TESTED:
            workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
            event = workflow.transition(
                WorkflowState.PATCH_PROPOSED,
                actor=actor,
                reason=f"Reviewer reported test failure for patch {patch_sha256}; another review is required.",
            )
            events.append(_event_dict(event))
            next_state = WorkflowState.PATCH_PROPOSED
        else:
            next_state = current
        events.append({
            "event_type": "test_result_recorded",
            "event_id": report_id,
            "workflow_id": workflow_id,
            "from_state": current.value,
            "to_state": next_state.value,
            "actor": actor,
            "reason": summary[:1000],
            "timestamp": now,
            "patch_sha256": patch_sha256,
            "outcome": outcome,
        })
        db.execute(
            """INSERT INTO test_reports
            (report_id, workflow_id, patch_sha256, outcome, command, summary, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_id, workflow_id, patch_sha256, outcome, command, summary, actor, now),
        )
        db.execute(
            "UPDATE debug_runs SET state = ?, updated_at = ?, events_json = ? WHERE workflow_id = ?",
            (next_state.value, now, json.dumps(events, separators=(",", ":")), workflow_id),
        )
        db.commit()
    return get_run(workflow_id)


def record_execution_result(
    workflow_id: str,
    *,
    patch_sha256: str,
    suite: str,
    outcome: str,
    exit_code: int | None,
    timed_out: bool,
    duration_seconds: float,
    workspace_sha256: str,
    output: str,
    output_truncated: bool,
    actor: str,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Persist an idempotent signed orchestrator result for the current patch."""
    initialise_store()
    if suite not in {"pytest", "ruff", "mypy"}:
        raise ValueError("Execution suite is not allow-listed.")
    if outcome not in {"passed", "failed", "timed_out"}:
        raise ValueError("Invalid execution outcome.")
    if outcome == "passed" and (exit_code != 0 or timed_out):
        raise ValueError("A passing result requires exit code zero and no timeout.")
    if outcome == "timed_out" and not timed_out:
        raise ValueError("Timed-out outcome must set timed_out=true.")
    if not actor.strip() or len(actor) > 120:
        raise ValueError("Actor must contain 1 to 120 characters.")
    if len(output) > 20000 or len(duration_seconds.__str__()) > 32:
        raise ValueError("Execution result exceeds safety limits.")
    report_id = execution_id or str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM execution_reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        if existing is not None:
            same_report = (
                existing["workflow_id"] == workflow_id
                and existing["patch_sha256"] == patch_sha256
                and existing["suite"] == suite
                and existing["outcome"] == outcome
                and existing["exit_code"] == exit_code
                and bool(existing["timed_out"]) == timed_out
                and float(existing["duration_seconds"]) == float(duration_seconds)
                and existing["workspace_sha256"] == workspace_sha256
                and existing["output"] == output
                and bool(existing["output_truncated"]) == output_truncated
                and existing["actor"] == actor
            )
            db.rollback()
            if same_report:
                return get_run(workflow_id)
            raise ValueError("Execution ID has already been used for a different result.")
        row = db.execute("SELECT * FROM debug_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(workflow_id)
        record = _decode_row(row)
        current = WorkflowState(record["state"])
        patch = db.execute(
            "SELECT patch_sha256 FROM patch_proposals WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 1",
            (workflow_id,),
        ).fetchone()
        if current not in {WorkflowState.PATCH_PROPOSED, WorkflowState.TESTED}:
            db.rollback()
            raise ValueError("Execution results can only be recorded for a proposed patch.")
        if patch is None or patch["patch_sha256"] != patch_sha256:
            db.rollback()
            raise ValueError("Execution result must reference the current patch SHA-256 digest.")
        events = record["events"]
        next_state = current
        if outcome == "passed" and current == WorkflowState.PATCH_PROPOSED:
            workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
            event = workflow.transition(
                WorkflowState.TESTED,
                actor=actor,
                reason=f"Isolated {suite} execution passed for patch {patch_sha256}.",
            )
            events.append(_event_dict(event))
            next_state = WorkflowState.TESTED
        elif outcome != "passed" and current == WorkflowState.TESTED:
            workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
            event = workflow.transition(
                WorkflowState.PATCH_PROPOSED,
                actor=actor,
                reason=f"Isolated {suite} execution did not pass; another review is required.",
            )
            events.append(_event_dict(event))
            next_state = WorkflowState.PATCH_PROPOSED
        events.append({
            "event_type": "execution_result_recorded",
            "event_id": report_id,
            "workflow_id": workflow_id,
            "from_state": current.value,
            "to_state": next_state.value,
            "actor": actor,
            "reason": f"Isolated {suite} execution outcome: {outcome}.",
            "timestamp": now,
            "patch_sha256": patch_sha256,
            "workspace_sha256": workspace_sha256,
            "suite": suite,
            "outcome": outcome,
            "exit_code": exit_code,
            "timed_out": timed_out,
        })
        db.execute(
            """INSERT INTO execution_reports
            (report_id, workflow_id, patch_sha256, suite, outcome, exit_code, timed_out,
             duration_seconds, workspace_sha256, output, output_truncated, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report_id, workflow_id, patch_sha256, suite, outcome, exit_code, int(timed_out),
                duration_seconds, workspace_sha256, output, int(output_truncated), actor, now,
            ),
        )
        db.execute(
            "UPDATE debug_runs SET state = ?, updated_at = ?, events_json = ? WHERE workflow_id = ?",
            (next_state.value, now, json.dumps(events, separators=(",", ":")), workflow_id),
        )
        db.commit()
    return get_run(workflow_id)


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "workflow_id": row["workflow_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "state": row["state"],
        "bug_report": row["bug_report"],
        "screenshot_sha256": row["screenshot_sha256"],
        "analysis": json.loads(row["analysis_json"]),
        "browser_evidence": json.loads(row["browser_evidence_json"]) if row["browser_evidence_json"] else None,
        "events": json.loads(row["events_json"]),
        "human_review_required": WorkflowState(row["state"]) not in TERMINAL_STATES,
    }

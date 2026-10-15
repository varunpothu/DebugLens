"""Small SQLite repository for durable local debugging runs and audit events.

Use a managed database and tenant-scoped authorisation before multi-user deployment.
"""
from __future__ import annotations

import json
import sqlite3
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
    if row is None:
        raise KeyError(workflow_id)
    return _decode_row(row)


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
        workflow = DebugWorkflow(workflow_id=workflow_id, state=current)
        try:
            event = workflow.transition(target, actor=actor, reason=reason)
        except ValueError:
            db.rollback()
            raise
        events.append(_event_dict(event))
        now = datetime.now(timezone.utc).isoformat()
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

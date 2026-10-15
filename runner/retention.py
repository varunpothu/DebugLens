"""Dry-run-first retention for terminal local DebugLens runs.

This utility deletes only old terminal runs and their relational child records. It does
not delete cloud artifacts, application logs, backups, or Docker worker containers.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.run_store import _connect, initialise_store

TERMINAL_STATES = ("verified", "rejected", "failed", "cancelled")
CHILD_TABLES = ("execution_reports", "test_reports", "patch_proposals")


def purge_expired_runs(
    *,
    retention_days: int = 90,
    apply: bool = False,
    actor: str = "retention-cli",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Count eligible runs by default; delete them only when apply=True."""
    if not 1 <= retention_days <= 3650:
        raise ValueError("retention_days must be between 1 and 3650.")
    if not actor.strip() or len(actor) > 120:
        raise ValueError("actor must contain 1 to 120 characters.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    cutoff = (current.astimezone(timezone.utc) - timedelta(days=retention_days)).isoformat()
    current_iso = current.astimezone(timezone.utc).isoformat()
    initialise_store()
    placeholders = ",".join("?" for _ in TERMINAL_STATES)
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            f"SELECT workflow_id FROM debug_runs WHERE state IN ({placeholders}) AND created_at < ? ORDER BY created_at",
            (*TERMINAL_STATES, cutoff),
        ).fetchall()
        workflow_ids = [str(row["workflow_id"]) for row in rows]
        if not apply:
            db.rollback()
            return {
                "mode": "dry_run",
                "retention_days": retention_days,
                "cutoff": cutoff,
                "eligible_runs": len(workflow_ids),
                "deleted_runs": 0,
                "message": "No data was deleted. Re-run with --apply to delete eligible terminal runs.",
            }

        db.execute(
            """CREATE TABLE IF NOT EXISTS retention_events (
                event_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                cutoff_at TEXT NOT NULL,
                retention_days INTEGER NOT NULL,
                deleted_run_count INTEGER NOT NULL,
                actor TEXT NOT NULL
            )"""
        )
        if workflow_ids:
            ids_sql = ",".join("?" for _ in workflow_ids)
            for table in CHILD_TABLES:
                db.execute(f"DELETE FROM {table} WHERE workflow_id IN ({ids_sql})", workflow_ids)
            db.execute(f"DELETE FROM debug_runs WHERE workflow_id IN ({ids_sql})", workflow_ids)
        from uuid import uuid4

        db.execute(
            """INSERT INTO retention_events
            (event_id, created_at, cutoff_at, retention_days, deleted_run_count, actor)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), current_iso, cutoff, retention_days, len(workflow_ids), actor.strip()),
        )
        db.commit()
    return {
        "mode": "apply",
        "retention_days": retention_days,
        "cutoff": cutoff,
        "eligible_runs": len(workflow_ids),
        "deleted_runs": len(workflow_ids),
        "actor": actor.strip(),
        "message": "Expired terminal runs and their patch/test/execution records were deleted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run-first cleanup of old terminal DebugLens runs.")
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--apply", action="store_true", help="Actually delete eligible local database records.")
    parser.add_argument("--actor", default="retention-cli", help="Operator label written to the retention audit table.")
    args = parser.parse_args()
    try:
        result = purge_expired_runs(
            retention_days=args.retention_days,
            apply=args.apply,
            actor=args.actor,
        )
    except (ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from datetime import datetime, timedelta, timezone

from app import run_store
from runner.retention import purge_expired_runs


def _insert_run(db, workflow_id: str, created_at: str, state: str) -> None:
    db.execute(
        """INSERT INTO debug_runs
        (workflow_id, created_at, updated_at, state, bug_report, screenshot_sha256,
         analysis_json, browser_evidence_json, events_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (workflow_id, created_at, created_at, state, "synthetic", "a" * 64, "{}", None, "[]"),
    )


def test_retention_is_dry_run_by_default_and_deletes_only_expired_terminal_runs(tmp_path, monkeypatch) -> None:
    database = tmp_path / "retention-test.db"
    monkeypatch.setattr(run_store, "_database_path", lambda: database)
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    old = (now - timedelta(days=120)).isoformat()
    recent = (now - timedelta(days=5)).isoformat()
    run_store.initialise_store()
    with run_store._connect() as db:
        _insert_run(db, "old-terminal", old, "rejected")
        _insert_run(db, "old-active", old, "human_review")
        _insert_run(db, "recent-terminal", recent, "verified")
        db.execute(
            """INSERT INTO patch_proposals
            (proposal_id, workflow_id, patch_sha256, patch_diff, rationale, risk, rollback_plan, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("proposal-1", "old-terminal", "b" * 64, "diff", "why", "low", "revert", "tester", old),
        )
        db.execute(
            """INSERT INTO test_reports
            (report_id, workflow_id, patch_sha256, outcome, command, summary, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("test-1", "old-terminal", "b" * 64, "passed", "pytest", "passed", "tester", old),
        )
        db.execute(
            """INSERT INTO execution_reports
            (report_id, workflow_id, patch_sha256, suite, outcome, exit_code, timed_out,
             duration_seconds, workspace_sha256, output, output_truncated, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("execution-1", "old-terminal", "b" * 64, "pytest", "passed", 0, 0, 1.0,
             "c" * 64, "ok", 0, "worker", old),
        )

    dry_run = purge_expired_runs(retention_days=90, now=now)
    assert dry_run["mode"] == "dry_run"
    assert dry_run["eligible_runs"] == 1
    assert dry_run["deleted_runs"] == 0

    with run_store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM debug_runs").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM patch_proposals").fetchone()[0] == 1

    applied = purge_expired_runs(retention_days=90, apply=True, actor="unit-test", now=now)
    assert applied["mode"] == "apply"
    assert applied["deleted_runs"] == 1
    with run_store._connect() as db:
        remaining = {row[0] for row in db.execute("SELECT workflow_id FROM debug_runs").fetchall()}
        assert remaining == {"old-active", "recent-terminal"}
        assert db.execute("SELECT COUNT(*) FROM patch_proposals").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM test_reports").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM execution_reports").fetchone()[0] == 0
        event = db.execute("SELECT deleted_run_count, actor FROM retention_events").fetchone()
        assert tuple(event) == (1, "unit-test")


def test_retention_rejects_invalid_age_and_naive_datetime() -> None:
    import pytest

    with pytest.raises(ValueError, match="retention_days"):
        purge_expired_runs(retention_days=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        purge_expired_runs(now=datetime(2026, 10, 15))

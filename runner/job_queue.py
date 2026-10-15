"""Durable local queue for isolated DebugLens test jobs.

The queue stores only local paths and non-secret metadata. It is intended for a trusted local
orchestrator, not as a public job-submission API.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ALLOWED_SUITES = {"pytest", "ruff", "mypy"}
OUTPUT_LIMIT = 20_000
MAX_ATTEMPTS = 2
LEASE_SECONDS = 420
POLL_SECONDS = 0.5
_STOP_EVENT = threading.Event()
REQUIRED_FIELDS = ("workspace", "patch_file", "manifest", "suite", "workflow_id", "actor", "api_url")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _database_path() -> Path:
    return Path(os.environ.get("DEBUGLENS_QUEUE_DATABASE", "./data/execution-queue.db")).expanduser()


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def initialise_queue() -> None:
    with _connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS execution_jobs (
                job_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN
                    ('queued','running','succeeded','failed','cancelled')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 2,
                worker_id TEXT,
                lease_until TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                dead_letter INTEGER NOT NULL DEFAULT 0,
                exit_code INTEGER,
                output TEXT NOT NULL DEFAULT ''
            )"""
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(execution_jobs)").fetchall()}
        if "dead_letter" not in columns:
            db.execute("ALTER TABLE execution_jobs ADD COLUMN dead_letter INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE INDEX IF NOT EXISTS idx_execution_jobs_claim ON execution_jobs(status, created_at)")


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "idempotency_key": row["idempotency_key"],
        "payload": json.loads(row["payload_json"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "worker_id": row["worker_id"],
        "lease_until": row["lease_until"],
        "cancel_requested": bool(row["cancel_requested"]),
        "dead_letter": bool(row["dead_letter"]),
        "exit_code": row["exit_code"],
        "output": row["output"],
    }


def validate_payload(payload: dict[str, Any]) -> dict[str, str]:
    if set(payload) != set(REQUIRED_FIELDS):
        raise ValueError(f"Job payload must contain exactly: {', '.join(REQUIRED_FIELDS)}.")
    result: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        value = payload[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            raise ValueError(f"{field} must be a non-empty string of at most 2048 characters.")
        result[field] = value.strip()
    if result["suite"] not in ALLOWED_SUITES:
        raise ValueError("suite must be one of pytest, ruff, mypy.")
    for field in ("workspace", "patch_file", "manifest"):
        result[field] = str(Path(result[field]).expanduser().absolute())
    if len(result["workflow_id"]) > 80 or len(result["actor"]) > 120:
        raise ValueError("workflow_id or actor exceeds the supported length.")
    return result


def enqueue_job(payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    initialise_queue()
    if not idempotency_key.strip() or len(idempotency_key) > 128:
        raise ValueError("Idempotency key must contain 1 to 128 characters.")
    validated = validate_payload(payload)
    idempotency_key = idempotency_key.strip()
    now = _timestamp()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM execution_jobs WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing is not None:
            if json.loads(existing["payload_json"]) != validated:
                db.rollback()
                raise ValueError("Idempotency key already exists with a different payload.")
            db.commit()
            return _decode(existing)
        job_id = str(uuid4())
        db.execute(
            """INSERT INTO execution_jobs
            (job_id,idempotency_key,payload_json,status,created_at,updated_at,max_attempts)
            VALUES(?,?,?,'queued',?,?,?)""",
            (job_id, idempotency_key, json.dumps(validated, sort_keys=True), now, now, MAX_ATTEMPTS),
        )
        db.commit()
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any]:
    initialise_queue()
    with _connect() as db:
        row = db.execute("SELECT * FROM execution_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return _decode(row)


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    initialise_queue()
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM execution_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_decode(row) for row in rows]


def request_cancel(job_id: str) -> dict[str, Any]:
    initialise_queue()
    now = _timestamp()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT status FROM execution_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(job_id)
        if row["status"] == "queued":
            db.execute(
                "UPDATE execution_jobs SET status='cancelled',updated_at=? WHERE job_id=?",
                (now, job_id),
            )
        elif row["status"] == "running":
            db.execute(
                "UPDATE execution_jobs SET cancel_requested=1,updated_at=? WHERE job_id=?",
                (now, job_id),
            )
        db.commit()
    return get_job(job_id)



def request_cancel_for_worker_prefix(worker_prefix: str) -> int:
    """Request cancellation only for jobs owned by this local worker process."""
    initialise_queue()
    now = _timestamp()
    with _connect() as db:
        cursor = db.execute(
            """UPDATE execution_jobs SET cancel_requested=1,updated_at=?
               WHERE status='running' AND substr(worker_id,1,?)=?""",
            (now, len(worker_prefix), worker_prefix),
        )
        return cursor.rowcount


def _recover_expired(db: sqlite3.Connection, now: datetime) -> None:
    rows = db.execute(
        "SELECT job_id, attempts, max_attempts, cancel_requested FROM execution_jobs "
        "WHERE status='running' AND lease_until < ?",
        (_timestamp(now),),
    ).fetchall()
    for row in rows:
        if row["cancel_requested"]:
            status = "cancelled"
        elif row["attempts"] < row["max_attempts"]:
            status = "queued"
        else:
            status = "failed"
        dead_letter = int(not row["cancel_requested"] and row["attempts"] >= row["max_attempts"])
        db.execute(
            """UPDATE execution_jobs SET status=?,worker_id=NULL,lease_until=NULL,
               dead_letter=MAX(dead_letter,?),updated_at=?,
               output=CASE WHEN output='' THEN ? ELSE output END WHERE job_id=?""",
            (status, dead_letter, _timestamp(now), "Worker lease expired; job recovered by queue.", row["job_id"]),
        )


def claim_next_job(worker_id: str, *, concurrency_limit: int = 1) -> dict[str, Any] | None:
    initialise_queue()
    if not worker_id.strip() or len(worker_id) > 160:
        raise ValueError("worker_id must contain 1 to 160 characters.")
    if not 1 <= concurrency_limit <= 16:
        raise ValueError("concurrency_limit must be between 1 and 16.")
    now = _now()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _recover_expired(db, now)
        running = db.execute(
            "SELECT COUNT(*) AS count FROM execution_jobs WHERE status='running'"
        ).fetchone()["count"]
        if running >= concurrency_limit:
            db.commit()
            return None
        row = db.execute(
            "SELECT * FROM execution_jobs WHERE status='queued' ORDER BY created_at,job_id LIMIT 1"
        ).fetchone()
        if row is None:
            db.commit()
            return None
        lease = _timestamp(now + timedelta(seconds=LEASE_SECONDS))
        db.execute(
            """UPDATE execution_jobs SET status='running',worker_id=?,lease_until=?,
               attempts=attempts+1,updated_at=? WHERE job_id=? AND status='queued'""",
            (worker_id, lease, _timestamp(now), row["job_id"]),
        )
        db.commit()
    return get_job(row["job_id"])


def heartbeat_job(job_id: str, worker_id: str) -> bool:
    initialise_queue()
    now = _now()
    with _connect() as db:
        cursor = db.execute(
            """UPDATE execution_jobs SET lease_until=?,updated_at=?
               WHERE job_id=? AND worker_id=? AND status='running'""",
            (_timestamp(now + timedelta(seconds=LEASE_SECONDS)), _timestamp(now), job_id, worker_id),
        )
        return cursor.rowcount == 1


def cancellation_requested(job_id: str, worker_id: str) -> bool:
    initialise_queue()
    with _connect() as db:
        row = db.execute(
            "SELECT cancel_requested,status,worker_id FROM execution_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
    if row is None:
        raise KeyError(job_id)
    return row["status"] != "running" or row["worker_id"] != worker_id or bool(row["cancel_requested"])


def finish_job(job_id: str, worker_id: str, *, exit_code: int, output: str) -> dict[str, Any]:
    initialise_queue()
    now = _timestamp()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM execution_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            db.rollback()
            raise KeyError(job_id)
        if row["status"] != "running" or row["worker_id"] != worker_id:
            db.rollback()
            raise ValueError("Only the current lease holder may finish this job.")
        if row["cancel_requested"]:
            status = "cancelled"
        elif exit_code == 0:
            status = "succeeded"
        elif exit_code == 2 and row["attempts"] < row["max_attempts"]:
            status = "queued"
        else:
            status = "failed"
        dead_letter = int(not row["cancel_requested"] and exit_code == 2 and row["attempts"] >= row["max_attempts"])
        db.execute(
            """UPDATE execution_jobs SET status=?,updated_at=?,worker_id=NULL,lease_until=NULL,
               exit_code=?,output=?,dead_letter=MAX(dead_letter,?) WHERE job_id=?""",
            (status, now, exit_code, output[:OUTPUT_LIMIT], dead_letter, job_id),
        )
        db.commit()
    return get_job(job_id)


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=8)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        process.terminate()
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            return
    try:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=8)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=3)


def _run_job(job: dict[str, Any], worker_id: str) -> dict[str, Any]:
    payload = job["payload"]
    command = [
        sys.executable, "-m", "runner.orchestrate",
        "--workspace", payload["workspace"],
        "--patch-file", payload["patch_file"],
        "--manifest", payload["manifest"],
        "--suite", payload["suite"],
        "--workflow-id", payload["workflow_id"],
        "--actor", payload["actor"],
        "--api-url", payload["api_url"],
    ]
    with tempfile.TemporaryFile(mode="w+b", dir="/tmp") as output_file:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                shell=False,
                close_fds=True,
                start_new_session=os.name == "posix",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        except OSError as exc:
            return finish_job(job["job_id"], worker_id, exit_code=2, output=str(exc))
        while process.poll() is None:
            if cancellation_requested(job["job_id"], worker_id):
                _stop_process(process)
                break
            heartbeat_job(job["job_id"], worker_id)
            time.sleep(POLL_SECONDS)
        exit_code = process.poll()
        if exit_code is None:
            exit_code = 130
        output_file.seek(0)
        output = output_file.read(OUTPUT_LIMIT + 1).decode("utf-8", errors="replace")
        if len(output) > OUTPUT_LIMIT:
            output = output[:OUTPUT_LIMIT] + "\n[output truncated]"
        return finish_job(job["job_id"], worker_id, exit_code=exit_code, output=output)


def worker_loop(*, worker_id: str, concurrency_limit: int = 1, once: bool = False) -> None:
    """Claim and execute jobs until idle (once=True) or interrupted."""
    initialise_queue()
    while not _STOP_EVENT.is_set():
        job = claim_next_job(worker_id, concurrency_limit=concurrency_limit)
        if job is None:
            if once:
                return
            time.sleep(POLL_SECONDS)
            continue
        _run_job(job, worker_id)
        if once:
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    enqueue = sub.add_parser("enqueue", help="Add a local isolated execution job")
    enqueue.add_argument("--workspace", required=True)
    enqueue.add_argument("--patch-file", required=True)
    enqueue.add_argument("--manifest", required=True)
    enqueue.add_argument("--suite", required=True, choices=sorted(ALLOWED_SUITES))
    enqueue.add_argument("--workflow-id", required=True)
    enqueue.add_argument("--actor", required=True)
    enqueue.add_argument("--api-url", default="http://127.0.0.1:8000")
    enqueue.add_argument("--idempotency-key", required=True)
    cancel = sub.add_parser("cancel", help="Cancel a queued or running job")
    cancel.add_argument("job_id")
    listing = sub.add_parser("list", help="List recent jobs")
    listing.add_argument("--limit", type=int, default=20)
    worker = sub.add_parser("worker", help="Run queue worker(s)")
    worker.add_argument("--concurrency", type=int, default=1)
    worker.add_argument("--once", action="store_true", help="Process at most one job then exit")
    args = parser.parse_args()
    try:
        if args.command == "enqueue":
            payload = {field: getattr(args, field) for field in REQUIRED_FIELDS}
            result = enqueue_job(payload, args.idempotency_key)
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "cancel":
            print(json.dumps(request_cancel(args.job_id), indent=2, sort_keys=True))
        elif args.command == "list":
            print(json.dumps(list_jobs(args.limit), indent=2, sort_keys=True))
        elif args.command == "worker":
            if not 1 <= args.concurrency <= 16:
                raise ValueError("concurrency must be between 1 and 16.")
            workers = [
                threading.Thread(
                    target=worker_loop,
                    kwargs={
                        "worker_id": f"{socket.gethostname()}-{os.getpid()}-{index}-{uuid4().hex[:8]}",
                        "concurrency_limit": args.concurrency,
                        "once": args.once,
                    },
                    daemon=False,
                )
                for index in range(args.concurrency)
            ]
            _STOP_EVENT.clear()
            for thread in workers:
                thread.start()
            try:
                for thread in workers:
                    thread.join()
            except KeyboardInterrupt:
                _STOP_EVENT.set()
                request_cancel_for_worker_prefix(f"{socket.gethostname()}-{os.getpid()}-")
                for thread in workers:
                    thread.join()
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(f"Queue operation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

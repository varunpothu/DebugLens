import sqlite3
from pathlib import Path

import pytest

from runner import job_queue


@pytest.fixture
def queue_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUGLENS_QUEUE_DATABASE", str(tmp_path / "queue.db"))
    job_queue.initialise_queue()


def payload() -> dict[str, str]:
    return {
        "workspace": "/tmp/reviewed",
        "patch_file": "/tmp/reviewed.patch",
        "manifest": "/tmp/manifest.json",
        "suite": "pytest",
        "workflow_id": "workflow-123",
        "actor": "local-reviewer",
        "api_url": "http://127.0.0.1:8000",
    }


def test_enqueue_is_idempotent_and_rejects_key_reuse_with_changed_payload(queue_db: None) -> None:
    first = job_queue.enqueue_job(payload(), "request-1")
    duplicate = job_queue.enqueue_job(payload(), "request-1")
    assert duplicate["job_id"] == first["job_id"]
    changed = payload()
    changed["suite"] = "ruff"
    with pytest.raises(ValueError, match="different payload"):
        job_queue.enqueue_job(changed, "request-1")


def test_claim_and_cancel_running_job(queue_db: None) -> None:
    queued = job_queue.enqueue_job(payload(), "request-2")
    claimed = job_queue.claim_next_job("worker-a", concurrency_limit=1)
    assert claimed is not None
    assert claimed["job_id"] == queued["job_id"]
    assert claimed["status"] == "running"
    cancelled = job_queue.request_cancel(queued["job_id"])
    assert cancelled["cancel_requested"] is True
    assert job_queue.cancellation_requested(queued["job_id"], "worker-a") is True
    finished = job_queue.finish_job(queued["job_id"], "worker-a", exit_code=130, output="cancelled")
    assert finished["status"] == "cancelled"


def test_cancel_queued_job_and_enforce_lease_owner(queue_db: None) -> None:
    queued = job_queue.enqueue_job(payload(), "request-3")
    assert job_queue.request_cancel(queued["job_id"])["status"] == "cancelled"
    assert job_queue.claim_next_job("worker-a") is None
    queued2 = job_queue.enqueue_job(payload() | {"workflow_id": "workflow-456"}, "request-4")
    claimed = job_queue.claim_next_job("worker-a")
    assert claimed is not None and claimed["job_id"] == queued2["job_id"]
    with pytest.raises(ValueError, match="lease holder"):
        job_queue.finish_job(queued2["job_id"], "worker-b", exit_code=0, output="")


def test_claims_respect_global_concurrency_limit(queue_db: None) -> None:
    job_queue.enqueue_job(payload(), "request-5")
    job_queue.enqueue_job(payload() | {"workflow_id": "workflow-789"}, "request-6")
    first = job_queue.claim_next_job("worker-a", concurrency_limit=1)
    assert first is not None
    assert job_queue.claim_next_job("worker-b", concurrency_limit=1) is None


def test_transient_worker_failure_is_retried_once_then_failed(queue_db: None) -> None:
    queued = job_queue.enqueue_job(payload(), "request-7")
    first = job_queue.claim_next_job("worker-a")
    assert first is not None
    retried = job_queue.finish_job(queued["job_id"], "worker-a", exit_code=2, output="temporary failure")
    assert retried["status"] == "queued"
    second = job_queue.claim_next_job("worker-b")
    assert second is not None
    failed = job_queue.finish_job(queued["job_id"], "worker-b", exit_code=2, output="again")
    assert failed["status"] == "failed"
    assert failed["dead_letter"] is True
    assert failed["attempts"] == 2
    assert job_queue.list_dead_letters()[0]["job_id"] == queued["job_id"]
    replayed = job_queue.replay_dead_letter(queued["job_id"])
    assert replayed["status"] == "queued"
    assert replayed["dead_letter"] is False
    assert replayed["attempts"] == 0


def test_payload_rejects_unapproved_suite_and_extra_fields(queue_db: None) -> None:
    with pytest.raises(ValueError, match="suite"):
        job_queue.enqueue_job(payload() | {"suite": "shell"}, "request-8")
    with pytest.raises(ValueError, match="exactly"):
        job_queue.enqueue_job(payload() | {"command": "anything"}, "request-9")


def test_expired_lease_recovers_job(queue_db: None) -> None:
    queued = job_queue.enqueue_job(payload(), "request-10")
    claimed = job_queue.claim_next_job("worker-a")
    assert claimed is not None
    with sqlite3.connect(job_queue._database_path()) as db:
        db.execute(
            "UPDATE execution_jobs SET lease_until='2000-01-01T00:00:00+00:00' WHERE job_id=?",
            (queued["job_id"],),
        )
    reclaimed = job_queue.claim_next_job("worker-b")
    assert reclaimed is not None
    assert reclaimed["job_id"] == queued["job_id"]
    assert reclaimed["attempts"] == 2

import hashlib
import hmac
import json
import subprocess
from pathlib import Path

import pytest

from runner import orchestrate


def worker_result() -> dict[str, object]:
    return {
        "schema_version": 1,
        "suite": "pytest",
        "outcome": "passed",
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 1.0,
        "workspace_sha256": "a" * 64,
        "output": "3 passed",
        "output_truncated": False,
    }


def test_signed_payload_binds_patch_suite_and_workspace() -> None:
    body, signature = orchestrate.signed_payload(
        workflow_id="run-123",
        patch_sha256="b" * 64,
        suite="pytest",
        result=worker_result(),
        actor="reviewer",
        secret="a-signing-secret-longer-than-thirty-two-characters",
    )
    expected = hmac.new(
        b"a-signing-secret-longer-than-thirty-two-characters",
        body,
        hashlib.sha256,
    ).hexdigest()
    payload = json.loads(body)
    assert signature == expected
    assert payload["patch_sha256"] == "b" * 64
    assert payload["workspace_sha256"] == "a" * 64
    assert payload["suite"] == "pytest"


def test_signed_payload_rejects_short_secret() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        orchestrate.signed_payload(
            workflow_id="run-123",
            patch_sha256="b" * 64,
            suite="pytest",
            result=worker_result(),
            actor="reviewer",
            secret="short",
        )


def test_execute_uses_network_disabled_read_only_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "reviewed"
    workspace.mkdir()
    monkeypatch.setattr(orchestrate, "workspace_digest", lambda root: "a" * 64)
    monkeypatch.setattr(
        orchestrate.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(worker_result()).encode("utf-8")
        ),
    )
    result, exit_code = orchestrate.execute(workspace=workspace, suite="pytest", image="worker:test")
    assert exit_code == 0
    assert result["outcome"] == "passed"


def test_submit_result_rejects_remote_plain_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        orchestrate.submit_result(
            api_url="http://localhost.evil.example",
            workflow_id="run-123",
            body=b"{}",
            signature="signature",
            api_token="",
        )

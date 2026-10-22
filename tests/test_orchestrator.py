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
    assert isinstance(payload["execution_id"], str) and len(payload["execution_id"]) == 36
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
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(worker_result()).encode("utf-8")
        )

    monkeypatch.setattr(orchestrate.subprocess, "run", fake_run)
    result, exit_code = orchestrate.execute(workspace=workspace, suite="pytest", image="worker:test")
    assert exit_code == 0
    assert result["outcome"] == "passed"
    assert "--network" in commands[0] and commands[0][commands[0].index("--network") + 1] == "none"
    assert "--read-only" in commands[0]
    assert "--init" in commands[0]
    assert commands[0][commands[0].index("--user") + 1] == "10001:10001"
    assert commands[0][commands[0].index("--network") + 1] == "none"
    assert commands[0][commands[0].index("--ulimit") + 1] == "nofile=1024:1024"
    assert "--name" in commands[0]


def test_execute_rejects_worker_digest_or_suite_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "reviewed"
    workspace.mkdir()
    monkeypatch.setattr(orchestrate, "workspace_digest", lambda root: "a" * 64)
    bad_result = worker_result()
    bad_result["workspace_sha256"] = "c" * 64
    monkeypatch.setattr(
        orchestrate.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(bad_result).encode("utf-8")
        ),
    )
    result, exit_code = orchestrate.execute(workspace=workspace, suite="pytest", image="worker:test")
    assert exit_code == 1
    assert result["outcome"] == "failed"
    assert "digest" in str(result["output"])


def test_submit_result_rejects_remote_plain_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        orchestrate.submit_result(
            api_url="http://localhost.evil.example",
            workflow_id="run-123",
            body=b"{}",
            signature="signature",
            api_token="",
        )



def test_execute_attempts_container_cleanup_after_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "reviewed"
    workspace.mkdir()
    monkeypatch.setattr(orchestrate, "workspace_digest", lambda root: "a" * 64)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        commands.append(command)
        if len(commands) == 1:
            raise subprocess.TimeoutExpired(command, timeout=30, output=b"partial output")
        return subprocess.CompletedProcess(command, 0, stdout=b"removed")

    monkeypatch.setattr(orchestrate.subprocess, "run", fake_run)
    result, exit_code = orchestrate.execute(
        workspace=workspace, suite="pytest", image="worker:test", timeout_seconds=30
    )
    assert exit_code == 1
    assert result["outcome"] == "timed_out"
    assert result["timed_out"] is True
    assert commands[1][:3] == ["docker", "rm", "-f"]
    assert commands[1][3] == commands[0][commands[0].index("--name") + 1]


def test_execute_reports_uncertain_cleanup_after_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "reviewed"
    workspace.mkdir()
    monkeypatch.setattr(orchestrate, "workspace_digest", lambda root: "a" * 64)
    calls = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(command, timeout=30, output=b"partial output")
        return subprocess.CompletedProcess(command, 1, stdout=b"cleanup failed")

    monkeypatch.setattr(orchestrate.subprocess, "run", fake_run)
    result, exit_code = orchestrate.execute(
        workspace=workspace, suite="pytest", image="worker:test", timeout_seconds=30
    )
    assert exit_code == 1
    assert result["outcome"] == "timed_out"
    assert "cleanup could not be confirmed" in str(result["output"])

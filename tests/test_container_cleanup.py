import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runner import container_cleanup


def _container_payload(*, created: datetime, label: bool = True) -> bytes:
    labels = {"com.debuglens.managed": "true"} if label else {}
    return json.dumps(
        [
            {
                "Id": "0123456789ab",
                "Name": "/debuglens-worker-test",
                "Created": created.isoformat().replace("+00:00", "Z"),
                "Config": {"Labels": labels},
                "State": {"Running": True},
            }
        ]
    ).encode("utf-8")


def test_cleanup_defaults_to_dry_run_and_only_targets_labelled_stale_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        if command[1:3] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(command, 0, stdout=b"0123456789ab\n")
        if command[1] == "inspect":
            return subprocess.CompletedProcess(
                command, 0, stdout=_container_payload(created=now - timedelta(hours=1))
            )
        return subprocess.CompletedProcess(command, 0, stdout=b"")

    monkeypatch.setattr(container_cleanup, "_run", fake_run)
    result = container_cleanup.cleanup_stale_containers(now=now)
    assert result == [
        {
            "id": "0123456789ab",
            "name": "debuglens-worker-test",
            "running": True,
            "age_seconds": 3600,
            "action": "would_remove",
        }
    ]
    assert not any(command[1:3] == ["rm", "-f"] for command in commands)


def test_cleanup_apply_removes_only_stale_managed_container(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        if command[1:3] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(command, 0, stdout=b"0123456789ab\n")
        if command[1] == "inspect":
            return subprocess.CompletedProcess(
                command, 0, stdout=_container_payload(created=now - timedelta(hours=1))
            )
        return subprocess.CompletedProcess(command, 0, stdout=b"")

    monkeypatch.setattr(container_cleanup, "_run", fake_run)
    result = container_cleanup.cleanup_stale_containers(apply=True, now=now)
    assert result[0]["action"] == "removed"
    assert ["docker", "rm", "-f", "0123456789ab"] in commands


def test_cleanup_skips_unlabelled_and_recent_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    inspected = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal inspected
        if command[1:3] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(command, 0, stdout=b"0123456789ab\n")
        inspected += 1
        payload = _container_payload(
            created=now - timedelta(minutes=5),
            label=False,
        )
        return subprocess.CompletedProcess(command, 0, stdout=payload)

    monkeypatch.setattr(container_cleanup, "_run", fake_run)
    assert container_cleanup.cleanup_stale_containers(apply=True, now=now) == []
    assert inspected == 1


def test_cleanup_rejects_unsafe_age_threshold() -> None:
    with pytest.raises(ValueError, match="between 600 seconds and 7 days"):
        container_cleanup.find_stale_containers(max_age_seconds=30)

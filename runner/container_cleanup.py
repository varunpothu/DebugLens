"""Safely inspect and optionally remove stale DebugLens worker containers.

This is an operator-invoked reconciliation tool. It defaults to dry-run and only considers
containers carrying the DebugLens management label.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any

MANAGED_LABEL = "com.debuglens.managed=true"
CONTAINER_ID = re.compile(r"^[0-9a-f]{12,64}$")
MIN_MAX_AGE_SECONDS = 600
MAX_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _run(command: list[str], *, timeout: int = 15) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            shell=False,
            close_fds=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Docker cleanup command failed to complete.") from exc


def find_stale_containers(
    *,
    max_age_seconds: int = 1800,
    now: datetime | None = None,
    docker: str = "docker",
) -> list[dict[str, Any]]:
    """Return labelled containers older than the threshold without removing anything."""
    if not MIN_MAX_AGE_SECONDS <= max_age_seconds <= MAX_MAX_AGE_SECONDS:
        raise ValueError("max_age_seconds must be between 600 seconds and 7 days.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware.")
    listed = _run([docker, "ps", "-aq", "--filter", f"label={MANAGED_LABEL}"])
    if listed.returncode != 0:
        raise RuntimeError("Unable to list managed Docker containers.")
    identifiers = [line.strip() for line in listed.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    stale: list[dict[str, Any]] = []
    for identifier in identifiers:
        if not CONTAINER_ID.fullmatch(identifier):
            continue
        inspected = _run([docker, "inspect", identifier])
        if inspected.returncode != 0:
            continue
        try:
            payload = json.loads(inspected.stdout.decode("utf-8", "strict"))
            if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
                continue
            container = payload[0]
            config = container.get("Config")
            state = container.get("State")
            if not isinstance(config, dict) or not isinstance(state, dict):
                continue
            labels = config.get("Labels")
            if not isinstance(labels, dict) or labels.get("com.debuglens.managed") != "true":
                continue
            created_raw = container.get("Created")
            if not isinstance(created_raw, str):
                continue
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if created.tzinfo is None:
                continue
        except (ValueError, TypeError, UnicodeDecodeError):
            continue
        age_seconds = (current - created).total_seconds()
        if age_seconds < max_age_seconds:
            continue
        name = container.get("Name")
        stale.append(
            {
                "id": identifier,
                "name": name.lstrip("/") if isinstance(name, str) else identifier,
                "running": state.get("Running") is True,
                "age_seconds": int(age_seconds),
            }
        )
    return stale


def cleanup_stale_containers(
    *,
    max_age_seconds: int = 1800,
    apply: bool = False,
    now: datetime | None = None,
    docker: str = "docker",
) -> list[dict[str, Any]]:
    """Dry-run by default; remove only previously identified, labelled stale containers."""
    stale = find_stale_containers(max_age_seconds=max_age_seconds, now=now, docker=docker)
    results: list[dict[str, Any]] = []
    for item in stale:
        result = dict(item)
        if not apply:
            result["action"] = "would_remove"
        else:
            removed = _run([docker, "rm", "-f", str(item["id"])])
            result["action"] = "removed" if removed.returncode == 0 else "remove_failed"
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-seconds", type=int, default=1800)
    parser.add_argument("--apply", action="store_true", help="Actually remove stale labelled containers.")
    args = parser.parse_args()
    try:
        results = cleanup_stale_containers(
            max_age_seconds=args.max_age_seconds,
            apply=args.apply,
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"dry_run": not args.apply, "containers": results}, indent=2))
    return 1 if any(item["action"] == "remove_failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

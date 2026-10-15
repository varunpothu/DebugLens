"""Bounded test worker intended to run only inside a disposable sandbox container.

This module deliberately exposes named suites, never arbitrary shell commands.
The container runtime must enforce network isolation and resource limits.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("DEBUGLENS_WORKSPACE", "/workspace")).resolve()
OUTPUT_LIMIT = 20_000
FILE_LIMIT = 10_000
WORKSPACE_BYTE_LIMIT = 50 * 1024 * 1024
SUITES: dict[str, tuple[str, ...]] = {
    "pytest": (sys.executable, "-m", "pytest", "-q", "--disable-warnings"),
    "ruff": (sys.executable, "-m", "ruff", "check", "."),
    "mypy": (sys.executable, "-m", "mypy", "app"),
}
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}


class WorkerInputError(ValueError):
    """The requested worker input is invalid or exceeds safety limits."""


def workspace_digest(root: Path = WORKSPACE) -> str:
    """Hash a bounded, deterministic snapshot of regular workspace files."""
    if not root.is_dir():
        raise WorkerInputError("Workspace directory is missing.")
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            raise WorkerInputError("Workspace symlinks are not allowed.")
        if not path.is_file():
            continue
        file_count += 1
        if file_count > FILE_LIMIT:
            raise WorkerInputError("Workspace contains too many files.")
        size = path.stat().st_size
        total_bytes += size
        if total_bytes > WORKSPACE_BYTE_LIMIT:
            raise WorkerInputError("Workspace exceeds the 50 MiB snapshot limit.")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def run_suite(suite: str, timeout_seconds: int = 120) -> dict[str, object]:
    """Run one fixed suite, capturing bounded output and a workspace digest."""
    if suite not in SUITES:
        raise WorkerInputError("Unknown suite. Allowed suites: pytest, ruff, mypy.")
    if not 1 <= timeout_seconds <= 300:
        raise WorkerInputError("Timeout must be between 1 and 300 seconds.")
    snapshot = workspace_digest()
    command = SUITES[suite]
    started = time.monotonic()
    outcome = "failed"
    exit_code: int | None = None
    timed_out = False
    with tempfile.TemporaryFile(mode="w+b", dir="/tmp") as output_file:
        try:
            completed = subprocess.run(
                command,
                cwd=WORKSPACE,
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
                shell=False,
                close_fds=True,
                env={
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "HOME": "/tmp",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONPATH": str(WORKSPACE),
                    "PYTEST_ADDOPTS": "-p no:cacheprovider",
                    "MYPY_CACHE_DIR": "/tmp/mypy_cache",
                    "RUFF_CACHE_DIR": "/tmp/ruff_cache",
                },
            )
            exit_code = completed.returncode
            outcome = "passed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            timed_out = True
            outcome = "timed_out"
        except OSError as exc:
            output_file.write(f"Worker could not start suite: {type(exc).__name__}".encode())
            outcome = "failed"
        output_file.flush()
        output_file.seek(0)
        output_bytes = output_file.read(OUTPUT_LIMIT + 1)
        truncated = len(output_bytes) > OUTPUT_LIMIT or output_file.tell() < output_file.seek(0, os.SEEK_END)
    elapsed = round(time.monotonic() - started, 3)
    output_text = output_bytes[:OUTPUT_LIMIT].decode("utf-8", errors="replace")
    return {
        "schema_version": 1,
        "suite": suite,
        "command": list(command),
        "outcome": outcome,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": elapsed,
        "workspace_sha256": snapshot,
        "output": output_text,
        "output_truncated": truncated,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_claim": "sandboxed_worker_required",
    }


def main() -> int:
    suite = os.environ.get("DEBUGLENS_TEST_SUITE", "")
    try:
        result = run_suite(suite)
    except WorkerInputError as exc:
        print(json.dumps({"schema_version": 1, "outcome": "rejected", "detail": str(exc)}))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

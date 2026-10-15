"""Host-side Docker orchestrator for signed, isolated test execution.

The signing secret stays on the trusted host and is never passed into the worker container.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

from runner.worker import workspace_digest

ALLOWED_SUITES = {"pytest", "ruff", "mypy"}
MAX_OUTPUT = 20_000


def execute(
    *,
    workspace: Path,
    suite: str,
    image: str,
    timeout_seconds: int = 330,
) -> tuple[dict[str, object], int]:
    """Execute the fixed suite inside a disposable, network-disabled Docker container."""
    workspace = workspace.expanduser()
    if workspace.is_symlink():
        raise ValueError("Workspace path must not itself be a symlink.")
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing real directory.")
    if "," in str(workspace):
        raise ValueError("Workspace paths containing commas are not supported by Docker --mount.")
    if suite not in ALLOWED_SUITES:
        raise ValueError("Suite must be one of: pytest, ruff, mypy.")
    if not 30 <= timeout_seconds <= 360:
        raise ValueError("Orchestrator timeout must be between 30 and 360 seconds.")

    snapshot = workspace_digest(workspace)
    command = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--memory", "512m",
        "--cpus", "1",
        "--pids-limit", "128",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--mount", f"type=bind,src={workspace},dst=/workspace,readonly",
        "-e", f"DEBUGLENS_TEST_SUITE={suite}",
        image,
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            close_fds=True,
        )
        output = completed.stdout.decode("utf-8", errors="replace")
        worker_result: dict[str, object] | None = None
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict) and parsed.get("schema_version") == 1:
                worker_result = parsed
        except json.JSONDecodeError:
            pass
        if worker_result is None:
            outcome = "failed"
            exit_code: int | None = completed.returncode
            output_text = output
            timed_out = False
            truncated = len(output_text) > MAX_OUTPUT
            output_text = output_text[:MAX_OUTPUT]
        else:
            outcome = str(worker_result.get("outcome", "failed"))
            exit_code = worker_result.get("exit_code") if isinstance(worker_result.get("exit_code"), int) else None
            output_text = str(worker_result.get("output", ""))[:MAX_OUTPUT]
            timed_out = bool(worker_result.get("timed_out", False))
            truncated = bool(worker_result.get("output_truncated", False))
            if outcome not in {"passed", "failed", "timed_out"}:
                outcome = "failed"
            if worker_result.get("suite") != suite or worker_result.get("workspace_sha256") != snapshot:
                outcome = "failed"
                output_text = "Worker result suite or workspace digest does not match the host snapshot."
                exit_code = completed.returncode
                timed_out = False
                truncated = False
            if outcome == "passed" and (completed.returncode != 0 or exit_code != 0 or timed_out):
                outcome = "failed"
    except subprocess.TimeoutExpired as exc:
        outcome = "timed_out"
        exit_code = None
        timed_out = True
        raw = exc.stdout or b""
        output_text = raw.decode("utf-8", errors="replace")[:MAX_OUTPUT]
        truncated = len(raw) > MAX_OUTPUT
    except OSError as exc:
        outcome = "failed"
        exit_code = None
        timed_out = False
        output_text = f"Docker execution could not start: {type(exc).__name__}"
        truncated = False

    result: dict[str, object] = {
        "schema_version": 1,
        "suite": suite,
        "outcome": outcome,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": min(round(time.monotonic() - started, 3), 360.0),
        "workspace_sha256": snapshot,
        "output": output_text,
        "output_truncated": truncated,
    }
    return result, (0 if outcome == "passed" else 1)


def verify_manifest(*, workspace: Path, manifest_path: Path, patch_file: Path) -> dict[str, object]:
    """Verify the provisioner manifest against the actual workspace and patch bytes."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("A valid DebugLens workspace manifest is required.")
    for field in ("base_revision", "base_workspace_sha256", "patch_sha256", "target_file", "workspace_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Workspace manifest is missing {field}.")
    for field in ("base_workspace_sha256", "patch_sha256", "workspace_sha256"):
        value = str(manifest[field])
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"Workspace manifest has an invalid {field}.")
    actual_patch_sha = hashlib.sha256(patch_file.read_bytes()).hexdigest()
    if not hmac.compare_digest(actual_patch_sha, str(manifest["patch_sha256"])):
        raise ValueError("Patch file digest does not match the workspace manifest.")
    actual_workspace_sha = workspace_digest(workspace.expanduser().resolve(strict=True))
    if not hmac.compare_digest(actual_workspace_sha, str(manifest["workspace_sha256"])):
        raise ValueError("Workspace digest does not match the workspace manifest.")
    return manifest


def signed_payload(
    *,
    workflow_id: str,
    patch_sha256: str,
    suite: str,
    result: dict[str, object],
    actor: str,
    secret: str,
) -> tuple[bytes, str]:
    """Bind a worker result to the caller-supplied current patch and sign canonical JSON."""
    if len(secret) < 32:
        raise ValueError("DEBUGLENS_EXECUTION_SIGNING_SECRET must contain at least 32 characters.")
    if len(patch_sha256) != 64 or any(char not in "0123456789abcdef" for char in patch_sha256):
        raise ValueError("patch_sha256 must be a lowercase SHA-256 hex digest.")
    payload = {
        "workflow_id": workflow_id,
        "patch_sha256": patch_sha256,
        "suite": suite,
        "outcome": result["outcome"],
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "duration_seconds": result["duration_seconds"],
        "workspace_sha256": result["workspace_sha256"],
        "output": result["output"],
        "output_truncated": result["output_truncated"],
        "actor": actor,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, signature


def submit_result(
    *,
    api_url: str,
    workflow_id: str,
    body: bytes,
    signature: str,
    api_token: str,
) -> int:
    """Submit the signed execution report over HTTPS (localhost HTTP is permitted for dev)."""
    base = api_url.rstrip("/")
    parsed = urlparse(base)
    local_http_hosts = {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (parsed.scheme == "http" and parsed.hostname not in local_http_hosts)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use HTTPS, or HTTP on localhost only, without URL credentials.")
    url = f"{base}/v1/debug-runs/{quote(workflow_id, safe='')}/execution-results"
    headers = {
        "Content-Type": "application/json",
        "X-DebugLens-Signature": signature,
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(response.read().decode("utf-8", errors="replace"))
            return 0 if response.status < 300 else 1
    except urllib.error.HTTPError as exc:
        print(f"API rejected execution report ({exc.code}): {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not submit execution report: {type(exc).__name__}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path, help="Reviewed source snapshot directory")
    parser.add_argument("--suite", required=True, choices=sorted(ALLOWED_SUITES))
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--patch-file", required=True, type=Path, help="Exact reviewed unified diff used to provision the workspace")
    parser.add_argument("--manifest", required=True, type=Path, help="Manifest produced by runner.provision")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    secret = os.environ.get("DEBUGLENS_EXECUTION_SIGNING_SECRET", "")
    api_token = os.environ.get("DEBUGLENS_API_ACCESS_TOKEN", "")
    try:
        manifest = verify_manifest(workspace=args.workspace, manifest_path=args.manifest, patch_file=args.patch_file)
        result, exit_code = execute(workspace=args.workspace, suite=args.suite, image="debuglens-test-worker:local")
        body, signature = signed_payload(
            workflow_id=args.workflow_id,
            patch_sha256=str(manifest["patch_sha256"]),
            suite=args.suite,
            result=result,
            actor=args.actor,
            secret=secret,
        )
        submit_status = submit_result(
            api_url=args.api_url,
            workflow_id=args.workflow_id,
            body=body,
            signature=signature,
            api_token=api_token,
        )
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return exit_code if submit_status == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

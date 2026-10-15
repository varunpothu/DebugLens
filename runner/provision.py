"""Create a deterministic, disposable workspace from a base tree and one reviewed diff.

This module never mutates the source tree and never executes source code. It applies a
strict, single-file unified diff with exact context matching and emits a digest manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from app.patch_suggester import validate_target_file
from runner.worker import workspace_digest

MAX_PATCH_BYTES = 200_000
MAX_FILES = 10_000
MAX_BYTES = 50 * 1024 * 1024
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", ".tox", ".idea", ".vscode",
}
EXCLUDED_FILES = {
    ".env", ".env.local", ".env.development", ".env.production",
    "debuglens.db", "debuglens-test.db", "test.db",
}
EXCLUDED_NAMES = {".aws", ".ssh", ".azure", ".gnupg"}



GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _git_output(source: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
            shell=False,
            close_fds=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("Unable to verify the source with Git.") from exc
    if result.returncode != 0:
        raise ProvisionError("Base workspace must be a valid local Git checkout.")
    return result.stdout.decode("utf-8", errors="strict").strip()


def verify_git_base(source: Path, expected_revision: str) -> str:
    """Require an exact commit SHA and a clean Git working tree."""
    if not GIT_SHA.fullmatch(expected_revision):
        raise ProvisionError("Base revision must be a full 40-character Git commit SHA.")
    top_level = Path(_git_output(source, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top_level != source.resolve(strict=True):
        raise ProvisionError("Base workspace must be the Git repository root.")
    actual_revision = _git_output(source, "rev-parse", "--verify", "HEAD^{commit}")
    if actual_revision != expected_revision:
        raise ProvisionError("Checked-out HEAD does not match the supplied base revision.")
    status = _git_output(source, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ProvisionError("Git working tree must be clean with no untracked files.")
    return actual_revision


class ProvisionError(ValueError):
    """The source tree or proposed patch cannot be safely provisioned."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part in EXCLUDED_DIRS or part in EXCLUDED_NAMES for part in parts):
        return True
    name = relative.name
    lower = name.lower()
    if lower in EXCLUDED_FILES:
        return True
    if lower.startswith(".env.") and lower != ".env.example":
        return True
    if lower.endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db")):
        return True
    if lower in {"id_rsa", "id_ed25519", "credentials", "secrets.json"}:
        return True
    return False


def _tracked_paths(source: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "ls-files", "--cached", "-z"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
            shell=False,
            close_fds=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("Unable to enumerate tracked source files.") from exc
    if result.returncode != 0:
        raise ProvisionError("Unable to enumerate tracked source files.")
    try:
        paths = {entry.decode("utf-8", errors="strict") for entry in result.stdout.split(bytes([0])) if entry}
    except UnicodeDecodeError as exc:
        raise ProvisionError("Tracked source paths must be UTF-8.") from exc
    if not paths:
        raise ProvisionError("Git base revision contains no tracked files.")
    if any(PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts for path in paths):
        raise ProvisionError("Git returned an unsafe tracked path.")
    return paths


def _copy_base(source: Path, destination: Path) -> tuple[int, int]:
    count = 0
    total = 0
    if source.is_symlink():
        raise ProvisionError("Base workspace path must not be a symlink.")
    source = source.resolve(strict=True)
    tracked = _tracked_paths(source)
    tracked_directories = {
        "/".join(PurePosixPath(item).parts[:index])
        for item in tracked
        for index in range(1, len(PurePosixPath(item).parts))
    }
    if not source.is_dir():
        raise ProvisionError("Base workspace must be an existing real directory.")
    destination.mkdir(parents=True, exist_ok=False)
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        root_path = Path(root)
        relative_root = root_path.relative_to(source)
        for dirname in list(dirs):
            path = root_path / dirname
            rel = relative_root / dirname
            rel_name = rel.as_posix()
            if path.is_symlink():
                if rel_name in tracked:
                    raise ProvisionError("Base workspace symlinks are not allowed.")
                dirs.remove(dirname)
                continue
            if _is_excluded(rel) or rel_name not in tracked_directories:
                dirs.remove(dirname)
        for filename in files:
            original = root_path / filename
            relative = relative_root / filename
            relative_name = relative.as_posix()
            if original.is_symlink():
                if relative_name in tracked:
                    raise ProvisionError("Base workspace symlinks are not allowed.")
                continue
            if relative_name not in tracked or _is_excluded(relative):
                continue
            if not original.is_file():
                raise ProvisionError("Base workspace may contain only regular files and directories.")
            count += 1
            total += original.stat().st_size
            if count > MAX_FILES or total > MAX_BYTES:
                raise ProvisionError("Base workspace exceeds the 10,000-file or 50 MiB limit.")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
    return count, total


def _apply_unified_diff(workspace: Path, patch_text: str, target_file: str) -> None:
    if not patch_text or len(patch_text.encode("utf-8")) > MAX_PATCH_BYTES:
        raise ProvisionError("Patch must contain 1 to 200,000 UTF-8 bytes.")
    target_file = validate_target_file(target_file)
    lines = patch_text.splitlines()
    expected_header = f"diff --git a/{target_file} b/{target_file}"
    if len(lines) < 4 or lines[0] != expected_header:
        raise ProvisionError("Patch must modify exactly the requested repository-relative file.")
    if lines[1] != f"--- a/{target_file}" or lines[2] != f"+++ b/{target_file}":
        raise ProvisionError("Patch file headers must match the requested target.")
    if any(line.startswith(("rename ", "copy ", "GIT binary patch", "Binary files ")) for line in lines):
        raise ProvisionError("Rename, copy, and binary patches are not supported.")
    source_path = workspace.joinpath(*PurePosixPath(target_file).parts)
    if source_path.is_symlink() or not source_path.is_file():
        raise ProvisionError("Patch target must be an existing regular file in the base workspace.")
    try:
        original_text = source_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise ProvisionError("Patch target must be readable UTF-8 text.") from exc
    original = original_text.splitlines()
    output: list[str] = []
    source_cursor = 0
    index = 3
    hunk_count = 0
    while index < len(lines):
        match = HUNK_HEADER.match(lines[index])
        if not match:
            raise ProvisionError("Patch contains unsupported or malformed unified-diff metadata.")
        old_start = int(match.group(1))
        new_start = int(match.group(3))
        old_count = int(match.group(2) or "1")
        new_count = int(match.group(4) or "1")
        if old_start < 1:
            raise ProvisionError("Patch hunk line numbers must reference an existing file.")
        hunk_start = old_start - 1
        if hunk_start < source_cursor or hunk_start > len(original):
            raise ProvisionError("Patch hunks overlap or reference lines outside the target.")
        output.extend(original[source_cursor:hunk_start])
        if new_start != len(output) + 1:
            raise ProvisionError("Patch hunk does not align with the new-file line numbers.")
        source_cursor = hunk_start
        old_seen = 0
        new_seen = 0
        index += 1
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if line.startswith("\\ No newline at end of file"):
                index += 1
                continue
            if not line or line[0] not in {" ", "+", "-"}:
                raise ProvisionError("Patch contains an invalid hunk line.")
            content = line[1:]
            if line[0] == " ":
                if source_cursor >= len(original) or original[source_cursor] != content:
                    raise ProvisionError("Patch context does not exactly match the base file.")
                output.append(content)
                source_cursor += 1
                old_seen += 1
                new_seen += 1
            elif line[0] == "-":
                if source_cursor >= len(original) or original[source_cursor] != content:
                    raise ProvisionError("Patch removal does not exactly match the base file.")
                source_cursor += 1
                old_seen += 1
            else:
                output.append(content)
                new_seen += 1
            index += 1
        if old_seen != old_count or new_seen != new_count:
            raise ProvisionError("Patch hunk line counts do not match its header.")
        hunk_count += 1
    if hunk_count == 0:
        raise ProvisionError("Patch must contain at least one change hunk.")
    output.extend(original[source_cursor:])
    final_text = "\n".join(output)
    if original_text.endswith("\n"):
        final_text += "\n"
    source_path.write_text(final_text, encoding="utf-8", newline="")


def provision_workspace(
    *,
    base_workspace: Path,
    patch_file: Path,
    target_file: str,
    output_workspace: Path,
    base_revision: str,
) -> dict[str, Any]:
    """Build a patched disposable workspace and return its external manifest."""
    base_workspace = base_workspace.expanduser()
    if base_workspace.is_symlink():
        raise ProvisionError("Base workspace path must not be a symlink.")
    base_workspace = base_workspace.resolve(strict=True)
    patch_file = patch_file.expanduser().resolve(strict=True)
    output_workspace = output_workspace.expanduser().absolute()
    if output_workspace.exists() or output_workspace.is_symlink():
        raise ProvisionError("Output workspace must not already exist.")
    output_workspace = output_workspace.parent.resolve(strict=False) / output_workspace.name
    if output_workspace == base_workspace or base_workspace in output_workspace.parents:
        raise ProvisionError("Output workspace must not be inside the source workspace.")
    verified_revision = verify_git_base(base_workspace, base_revision.strip())
    patch_bytes = patch_file.read_bytes()
    if len(patch_bytes) > MAX_PATCH_BYTES:
        raise ProvisionError("Patch exceeds the 200,000-byte limit.")
    try:
        patch_text = patch_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProvisionError("Patch must be UTF-8 text.") from exc
    output_workspace.parent.mkdir(parents=True, exist_ok=True)
    try:
        _copy_base(base_workspace, output_workspace)
        base_digest = workspace_digest(output_workspace)
        _apply_unified_diff(output_workspace, patch_text, target_file)
        final_digest = workspace_digest(output_workspace)
    except Exception:
        shutil.rmtree(output_workspace, ignore_errors=True)
        raise
    return {
        "schema_version": 1,
        "base_revision": verified_revision,
        "base_workspace_sha256": base_digest,
        "patch_sha256": sha256_bytes(patch_bytes),
        "target_file": validate_target_file(target_file),
        "workspace_sha256": final_digest,
        "file_count": sum(1 for path in output_workspace.rglob("*") if path.is_file()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-workspace", required=True, type=Path)
    parser.add_argument("--patch-file", required=True, type=Path)
    parser.add_argument("--target-file", required=True)
    parser.add_argument("--output-workspace", required=True, type=Path)
    parser.add_argument("--base-revision", required=True, help="Exact 40-character SHA of the clean Git HEAD")
    parser.add_argument("--manifest", required=True, type=Path, help="Manifest path outside the output workspace")
    args = parser.parse_args()
    try:
        manifest_path = args.manifest.expanduser().absolute()
        output_path = args.output_workspace.expanduser().absolute()
        if manifest_path == output_path or output_path in manifest_path.parents:
            raise ProvisionError("Manifest must be outside the output workspace.")
        manifest = provision_workspace(
            base_workspace=args.base_workspace,
            patch_file=args.patch_file,
            target_file=args.target_file,
            output_workspace=output_path,
            base_revision=args.base_revision,
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(manifest, separators=(",", ":"), sort_keys=True))
    except (OSError, ValueError) as exc:
        print(f"Workspace provisioning failed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from runner import provision as provision_module
from runner.orchestrate import verify_manifest
from runner.provision import ProvisionError, provision_workspace
from runner.worker import workspace_digest


PATCH = (
    "diff --git a/app.css b/app.css\n"
    "--- a/app.css\n"
    "+++ b/app.css\n"
    "@@ -1 +1 @@\n"
    ".button { width: 118%; }\n"
    "+.button { max-width: 100%; }\n"
)
# The replacement patch uses a removal plus an addition.
PATCH = PATCH.replace(
    ".button { width: 118%; }\n+.button { max-width: 100%; }",
    "-.button { width: 118%; }\n+.button { max-width: 100%; }",
)


def prepare(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "base"
    base.mkdir()
    (base / "app.css").write_text(".button { width: 118%; }\n", encoding="utf-8")
    (base / ".env").write_text("SECRET=never-copy\n", encoding="utf-8")
    (base / ".env.example").write_text("EXAMPLE=value\n", encoding="utf-8")
    patch = tmp_path / "reviewed.patch"
    patch.write_text(PATCH, encoding="utf-8")
    if shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(base)], check=True)
        subprocess.run(["git", "-C", str(base), "config", "user.email", "debuglens-test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(base), "config", "user.name", "DebugLens Tests"], check=True)
        subprocess.run(["git", "-C", str(base), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(base), "commit", "-qm", "test base snapshot"], check=True)
    return base, patch


@pytest.fixture(autouse=True)
def stub_git_verification_when_git_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("git") is None:
        monkeypatch.setattr(provision_module, "verify_git_base", lambda source, expected: expected)


def revision(base: Path) -> str:
    if not shutil.which("git"):
        return "a" * 40
    return subprocess.run(
        ["git", "-C", str(base), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_provision_creates_exact_patched_copy_without_mutating_base(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    output = tmp_path / "workspace"
    manifest = provision_workspace(
        base_workspace=base,
        patch_file=patch,
        target_file="app.css",
        output_workspace=output,
        base_revision=revision(base),
    )
    assert (base / "app.css").read_text(encoding="utf-8") == ".button { width: 118%; }\n"
    assert (output / "app.css").read_text(encoding="utf-8") == ".button { max-width: 100%; }\n"
    assert not (output / ".env").exists()
    assert (output / ".env.example").exists()
    assert manifest["patch_sha256"] == sha256(patch.read_bytes()).hexdigest()
    assert manifest["workspace_sha256"] == workspace_digest(output)
    assert manifest["base_revision"] == revision(base)



@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed in the restricted worker image")\ndef test_provision_requires_matching_clean_git_revision(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    with pytest.raises(ProvisionError, match="does not match"):
        provision_workspace(
            base_workspace=base,
            patch_file=patch,
            target_file="app.css",
            output_workspace=tmp_path / "wrong-revision",
            base_revision="0" * 40,
        )
    (base / "dirty.txt").write_text("uncommitted", encoding="utf-8")
    with pytest.raises(ProvisionError, match="working tree must be clean"):
        provision_workspace(
            base_workspace=base,
            patch_file=patch,
            target_file="app.css",
            output_workspace=tmp_path / "dirty-worktree",
            base_revision=revision(base),
        )

def test_provision_rejects_context_mismatch_and_cleans_output(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    patch.write_text(PATCH.replace("118%", "119%"), encoding="utf-8")
    output = tmp_path / "workspace"
    with pytest.raises(ProvisionError, match="exactly match"):
        provision_workspace(
            base_workspace=base,
            patch_file=patch,
            target_file="app.css",
            output_workspace=output,
            base_revision=revision(base),
        )
    assert not output.exists()



def test_provision_rejects_inconsistent_new_file_line_numbers(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    patch.write_text(PATCH.replace("@@ -1 +1 @@", "@@ -1 +2 @@"), encoding="utf-8")
    with pytest.raises(ProvisionError, match="new-file line numbers"):
        provision_workspace(
            base_workspace=base,
            patch_file=patch,
            target_file="app.css",
            output_workspace=tmp_path / "workspace",
            base_revision="deadbeef",
        )


def test_provision_rejects_path_traversal_and_symlinks(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    with pytest.raises(ValueError):
        provision_workspace(
            base_workspace=base,
            patch_file=patch,
            target_file="../app.css",
            output_workspace=tmp_path / "workspace",
            base_revision="deadbeef",
        )
    link = base / "linked.txt"
    link.symlink_to(base / "app.css")
    if shutil.which("git"):
        subprocess.run(["git", "-C", str(base), "add", "linked.txt"], check=True)
        subprocess.run(["git", "-C", str(base), "commit", "-qm", "add symlink fixture"], check=True)
    with pytest.raises(ProvisionError, match="symlinks"):
        provision_workspace(
            base_workspace=base,
            patch_file=patch,
            target_file="app.css",
            output_workspace=tmp_path / "workspace2",
            base_revision="deadbeef",
        )


def test_manifest_verification_binds_patch_and_workspace(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    workspace = tmp_path / "workspace"
    manifest = provision_workspace(
        base_workspace=base,
        patch_file=patch,
        target_file="app.css",
        output_workspace=workspace,
        base_revision="deadbeef",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_manifest(workspace=workspace, manifest_path=manifest_path, patch_file=patch)["patch_sha256"] == manifest["patch_sha256"]
    (workspace / "app.css").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Workspace digest"):
        verify_manifest(workspace=workspace, manifest_path=manifest_path, patch_file=patch)

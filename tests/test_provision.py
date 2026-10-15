import json
from hashlib import sha256
from pathlib import Path

import pytest

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
    return base, patch


def test_provision_creates_exact_patched_copy_without_mutating_base(tmp_path: Path) -> None:
    base, patch = prepare(tmp_path)
    output = tmp_path / "workspace"
    manifest = provision_workspace(
        base_workspace=base,
        patch_file=patch,
        target_file="app.css",
        output_workspace=output,
        base_revision="deadbeef",
    )
    assert (base / "app.css").read_text(encoding="utf-8") == ".button { width: 118%; }\n"
    assert (output / "app.css").read_text(encoding="utf-8") == ".button { max-width: 100%; }\n"
    assert not (output / ".env").exists()
    assert (output / ".env.example").exists()
    assert manifest["patch_sha256"] == sha256(patch.read_bytes()).hexdigest()
    assert manifest["workspace_sha256"] == workspace_digest(output)
    assert manifest["base_revision"] == "deadbeef"


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
            base_revision="deadbeef",
        )
    assert not output.exists()


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

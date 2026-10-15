from pathlib import Path

import pytest

from runner.worker import WorkerInputError, run_suite, workspace_digest


def test_workspace_digest_is_stable_and_changes_with_file_content(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    first = workspace_digest(tmp_path)
    assert first == workspace_digest(tmp_path)
    source.write_text("value = 2\n", encoding="utf-8")
    assert workspace_digest(tmp_path) != first


def test_workspace_digest_ignores_generated_cache_directories(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    before = workspace_digest(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "generated.pyc").write_bytes(b"ignored")
    assert workspace_digest(tmp_path) == before


def test_workspace_digest_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("data", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(target)
    with pytest.raises(WorkerInputError, match="symlinks"):
        workspace_digest(tmp_path)


def test_worker_rejects_arbitrary_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("runner.worker.WORKSPACE", Path("."))
    with pytest.raises(WorkerInputError, match="Unknown suite"):
        run_suite("bash -c rm -rf /")


def test_worker_rejects_out_of_range_timeout() -> None:
    with pytest.raises(WorkerInputError, match="Timeout"):
        run_suite("pytest", timeout_seconds=301)

import json
from pathlib import Path

import pytest
from PIL import Image

from app.benchmark import BenchmarkInputError, load_manifest, run_benchmark


def make_manifest(root: Path, expected: list[str]) -> Path:
    Image.new("RGB", (12, 12), "white").save(root / "screen.png")
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "dataset_version": "synthetic-test-v1",
        "cases": [{
            "id": "synthetic-001",
            "image": "screen.png",
            "bug_report": "Synthetic test fixture",
            "expected_categories": expected,
        }],
    }), encoding="utf-8")
    return manifest


def test_benchmark_calculates_category_metrics(tmp_path, monkeypatch) -> None:
    from app.schemas import AnalysisResponse, Finding, Severity

    manifest = make_manifest(tmp_path, ["layout", "accessibility"])
    response = AnalysisResponse(
        provider="mock",
        provider_version="test-model",
        screenshot_sha256="a" * 64,
        screenshot_width=12,
        screenshot_height=12,
        bug_report="Synthetic test fixture",
        findings=[
            Finding(
                title="Button clipped",
                severity=Severity.MEDIUM,
                confidence=0.7,
                category="layout",
                summary="Synthetic finding",
                evidence=[],
                hypotheses=[],
                recommended_checks=[],
            ),
            Finding(
                title="Extra colour issue",
                severity=Severity.LOW,
                confidence=0.6,
                category="colour",
                summary="Synthetic finding",
                evidence=[],
                hypotheses=[],
                recommended_checks=[],
            ),
        ],
        test_plan=[],
        limitations=[],
    )
    monkeypatch.setattr("app.benchmark.analyse_screenshot", lambda *args: response)
    report = run_benchmark(manifest, "anthropic")
    assert report["completed_count"] == 1
    assert report["failed_count"] == 0
    assert report["category_metrics"]["layout"]["recall"] == 1.0
    assert report["category_metrics"]["accessibility"]["recall"] == 0.0
    assert report["category_metrics"]["colour"]["precision"] == 0.0
    assert report["macro_f1"] >= 0.0


def test_manifest_rejects_path_traversal(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "dataset_version": "synthetic-test-v1",
        "cases": [{
            "id": "unsafe",
            "image": "../outside.png",
            "expected_categories": [],
        }],
    }), encoding="utf-8")
    with pytest.raises(BenchmarkInputError):
        load_manifest(manifest)


def test_manifest_requires_unique_case_ids(tmp_path) -> None:
    Image.new("RGB", (2, 2), "white").save(tmp_path / "screen.png")
    manifest = tmp_path / "manifest.json"
    case = {"id": "duplicate", "image": "screen.png", "expected_categories": []}
    manifest.write_text(json.dumps({"schema_version": 1, "dataset_version": "synthetic-test-v1", "cases": [case, case]}), encoding="utf-8")
    with pytest.raises(BenchmarkInputError, match="unique"):
        load_manifest(manifest)



def test_benchmark_rejects_mock_provider(tmp_path) -> None:
    from app.benchmark import run_benchmark

    manifest = make_manifest(tmp_path, [])
    with pytest.raises(BenchmarkInputError, match="non-diagnostic"):
        run_benchmark(manifest, "mock")

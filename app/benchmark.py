"""Reproducible benchmark runner for labelled, consented screenshot fixtures.

Reports category-level detection metrics and operational failures. It does not claim root-cause
accuracy or localisation accuracy, and never copies screenshot bytes into the output report.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.services.analyzer import analyse_screenshot


class BenchmarkInputError(ValueError):
    """Raised when the benchmark manifest or fixture paths are unsafe or invalid."""


def _safe_fixture_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise BenchmarkInputError("Fixture image paths must be relative to the benchmark root.")
    candidate = root / relative
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise BenchmarkInputError("Fixture image must remain inside the benchmark root.") from exc
    if candidate.is_symlink():
        raise BenchmarkInputError("Symlinked benchmark fixtures are not allowed.")
    if not resolved.is_file():
        raise BenchmarkInputError("Fixture image must be a regular file.")
    if resolved.stat().st_size > 10 * 1024 * 1024:
        raise BenchmarkInputError("Fixture image exceeds the 10 MiB benchmark limit.")
    return resolved


def load_manifest(manifest_path: Path) -> tuple[Path, list[dict[str, Any]]]:
    """Load a JSON manifest whose image paths resolve within its containing directory."""
    manifest = manifest_path.expanduser().resolve(strict=True)
    root = manifest.parent
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkInputError("Benchmark manifest is not readable valid JSON.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("dataset_version"), str)
        or not payload["dataset_version"].strip()
    ):
        raise BenchmarkInputError("Manifest must include schema_version=1 and a non-empty dataset_version.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkInputError("Manifest must contain at least one benchmark case.")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise BenchmarkInputError("Every benchmark case must be an object.")
        case_id = case.get("id")
        image = case.get("image")
        categories = case.get("expected_categories")
        bug_report = case.get("bug_report", "")
        if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 120:
            raise BenchmarkInputError("Each case requires a short non-empty id.")
        if case_id in seen:
            raise BenchmarkInputError("Benchmark case IDs must be unique.")
        seen.add(case_id)
        if not isinstance(image, str) or not image.strip():
            raise BenchmarkInputError("Each case requires a relative image path.")
        if (
            not isinstance(categories, list)
            or any(not isinstance(value, str) or not value.strip() for value in categories)
        ):
            raise BenchmarkInputError("expected_categories must be a list of non-empty strings.")
        if not isinstance(bug_report, str) or len(bug_report) > 4000:
            raise BenchmarkInputError("bug_report must be a string no longer than 4000 characters.")
        _safe_fixture_path(root, image)
        validated.append({
            "id": case_id,
            "image": image,
            "expected_categories": sorted({value.strip().lower() for value in categories}),
            "bug_report": bug_report,
        })
    return root, validated


def run_benchmark(manifest_path: Path, provider: str) -> dict[str, Any]:
    """Run a fixed provider on a labelled manifest and return aggregate detection metrics."""
    if provider == "mock":
        raise BenchmarkInputError("Mock mode is non-diagnostic and cannot produce meaningful benchmark metrics.")
    root, cases = load_manifest(manifest_path)
    per_case: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    completed = 0
    failed = 0

    for case in cases:
        image_path = _safe_fixture_path(root, case["image"])
        try:
            response = analyse_screenshot(image_path.read_bytes(), case["bug_report"] or None, provider)
            predicted = {
                finding.category.strip().lower()
                for finding in response.findings
                if finding.category.strip().lower() not in {"analysis_limit"}
            }
            expected = set(case["expected_categories"])
            categories = expected | predicted
            for category in categories:
                if category in expected and category in predicted:
                    counts[category]["tp"] += 1
                elif category in predicted:
                    counts[category]["fp"] += 1
                else:
                    counts[category]["fn"] += 1
            completed += 1
            per_case.append({
                "case_id": case["id"],
                "status": "completed",
                "expected_categories": sorted(expected),
                "predicted_categories": sorted(predicted),
                "exact_category_match": expected == predicted,
                "provider_version": response.provider_version,
            })
        except Exception as exc:
            failed += 1
            # Do not serialize provider exceptions or sensitive fixture contents.
            per_case.append({
                "case_id": case["id"],
                "status": "failed",
                "error_code": "provider_unavailable" if isinstance(exc, RuntimeError) else "case_failed",
            })
            for category in case["expected_categories"]:
                counts[category]["fn"] += 1

    metrics: dict[str, Any] = {}
    for category, value in sorted(counts.items()):
        tp, fp, fn = value["tp"], value["fp"], value["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics[category] = {
            **value,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    macro_f1 = (
        sum(item["f1"] for item in metrics.values()) / len(metrics)
        if metrics else 0.0
    )
    return {
        "schema_version": 1,
        "provider": provider,
        "dataset_version": json.loads(manifest_path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))["dataset_version"],
        "case_count": len(cases),
        "completed_count": completed,
        "failed_count": failed,
        "category_metrics": metrics,
        "macro_f1": round(macro_f1, 4),
        "cases": per_case,
        "limitations": [
            "Category-level metrics do not measure evidence quality, localisation, or root-cause correctness.",
            "A category match is not proof that the diagnosis is correct.",
            "Benchmark quality depends on representative labels, independent adjudication, and leakage-resistant splits.",
            "Use only synthetic, redacted, consented fixtures and review provider transfer settings.",
        ],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a labelled DebugLens screenshot benchmark.")
    parser.add_argument("manifest", type=Path, help="Path to the versioned JSON manifest.")
    parser.add_argument("--provider", required=True, choices=["mock", "openai_compatible", "anthropic", "gemini"])
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()
    report = run_benchmark(args.manifest, args.provider)
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 1 if report["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

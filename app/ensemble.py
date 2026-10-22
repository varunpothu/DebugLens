"""Multi-model comparison with explicit disagreement reporting.

Agreement is a review signal, not ground truth. This module never suppresses minority findings
and never turns model confidence into a correctness probability.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from time import perf_counter
from typing import Any

from app.services.analyzer import ProviderConsentRequired, analyse_screenshot
from app.providers.budget import ProviderRateLimitError


@dataclass(frozen=True, slots=True)
class ProviderRun:
    provider: str
    status: str
    latency_ms: float
    model_version: str | None
    findings: list[dict[str, Any]]
    prompt_version: str | None = None
    error_code: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None
    retry_after_seconds: int | None = None


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalise(left), _normalise(right)).ratio()


def _compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("category") != right.get("category"):
        return False
    title_score = _similarity(str(left.get("title", "")), str(right.get("title", "")))
    summary_score = _similarity(str(left.get("summary", "")), str(right.get("summary", "")))
    return title_score >= 0.62 or summary_score >= 0.78


def compare_ensemble(
    image_bytes: bytes,
    bug_report: str | None,
    providers: list[str],
) -> dict[str, Any]:
    """Run each explicitly selected provider and retain both agreement and disagreement."""
    if not providers:
        raise ValueError("Select at least one provider.")
    if len(providers) > 4:
        raise ValueError("At most four providers can be compared in one run.")
    if len(set(providers)) != len(providers):
        raise ValueError("Provider names must be unique in a comparison.")

    runs: list[ProviderRun] = []
    for provider in providers:
        started = perf_counter()
        try:
            response = analyse_screenshot(image_bytes, bug_report, provider)
            runs.append(
                ProviderRun(
                    provider=provider,
                    status="completed",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    model_version=response.provider_version,
                    findings=[item.model_dump(mode="json") for item in response.findings],
                    prompt_version=response.prompt_version,
                    usage_input_tokens=response.usage_input_tokens,
                    usage_output_tokens=response.usage_output_tokens,
                )
            )
        except ProviderRateLimitError as exc:
            runs.append(
                ProviderRun(
                    provider=provider,
                    status="failed",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    model_version=None,
                    findings=[],
                    error_code="provider_rate_limited",
                    retry_after_seconds=exc.retry_after_seconds,
                )
            )
        except ProviderConsentRequired:
            runs.append(
                ProviderRun(
                    provider=provider,
                    status="failed",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    model_version=None,
                    findings=[],
                    error_code="provider_consent_required",
                )
            )
        except Exception as exc:
            error_code = "provider_unavailable" if isinstance(exc, RuntimeError) else "analysis_failed"
            runs.append(
                ProviderRun(
                    provider=provider,
                    status="failed",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    model_version=None,
                    findings=[],
                    error_code=error_code,
                )
            )

    clusters: list[dict[str, Any]] = []
    for run in runs:
        if run.status != "completed":
            continue
        for finding in run.findings:
            match = next(
                (cluster for cluster in clusters if _compatible(cluster["representative"], finding)),
                None,
            )
            if match is None:
                match = {
                    "cluster_id": f"F-{len(clusters) + 1:03d}",
                    "representative": finding,
                    "provider_observations": [],
                }
                clusters.append(match)
            match["provider_observations"].append(
                {
                    "provider": run.provider,
                    "title": finding.get("title"),
                    "severity": finding.get("severity"),
                    "confidence": finding.get("confidence"),
                    "evidence": finding.get("evidence", []),
                }
            )

    for cluster in clusters:
        observations = cluster["provider_observations"]
        provider_names = [item["provider"] for item in observations]
        cluster["supporting_provider_count"] = len(set(provider_names))
        cluster["supporting_providers"] = sorted(set(provider_names))
        cluster["severity_distribution"] = dict(
            Counter(str(item["severity"]) for item in observations)
        )
        cluster["agreement_label"] = (
            "single-provider signal"
            if len(set(provider_names)) == 1
            else "cross-provider corroboration"
        )
        cluster.pop("representative", None)

    completed = [run for run in runs if run.status == "completed"]
    return {
        "schema_version": 1,
        "providers_requested": providers,
        "providers_completed": len(completed),
        "providers_failed": len(runs) - len(completed),
        "provider_runs": [asdict(run) for run in runs],
        "finding_clusters": clusters,
        "unresolved_disagreement_count": sum(
            1 for cluster in clusters if cluster["supporting_provider_count"] == 1
        ),
        "assurance": {
            "human_review_required": True,
            "agreement_is_not_ground_truth": True,
            "confidence_values_are_not_cross_model_calibrated": True,
            "minority_findings_preserved": True,
            "automatic_patch_execution": False,
        },
        "limitations": [
            "Semantic clustering is heuristic and can merge distinct defects or split equivalent findings.",
            "Different models can share failure modes; agreement does not establish correctness.",
            "A provider failure is not evidence that the provider found no defects.",
            "Provider confidence values are preserved per finding and are not averaged across models.",
        ],
    }

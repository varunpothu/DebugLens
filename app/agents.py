"""Bounded investigation stages that turn model output into a reviewable plan.

These are deterministic orchestration stages, not autonomous LLM agents. They never execute code,
claim tests passed, modify repositories, or override human approval.
"""
from __future__ import annotations

from typing import Any


def build_investigation_pipeline(
    analysis: dict[str, Any],
    browser_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build evidence summary, ranked hypotheses, test candidates, and assurance gates."""
    findings = analysis.get("findings") or []
    evidence_items: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    test_cases: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            continue
        title = str(finding.get("title") or f"Finding {index}")[:160]
        severity = str(finding.get("severity") or "info").lower()
        try:
            confidence = max(0.0, min(1.0, float(finding.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), list) else []
        observed = [item for item in evidence if isinstance(item, dict) and item.get("observed") is True]
        for item in evidence:
            if isinstance(item, dict):
                evidence_items.append({
                    "finding": title,
                    "source": str(item.get("source") or "unknown")[:80],
                    "description": str(item.get("description") or "")[:500],
                    "observed": item.get("observed") is True,
                })
        raw_hypotheses = finding.get("hypotheses")
        hypothesis_items = raw_hypotheses if isinstance(raw_hypotheses, list) else []
        for hypothesis in hypothesis_items[:10]:
            hypotheses.append({
                "finding": title,
                "severity": severity,
                "confidence": confidence,
                "hypothesis": str(hypothesis)[:500],
                "status": "unverified",
            })
        if severity in {"high", "critical"}:
            blockers.append(f"High-impact finding requires explicit reviewer confirmation: {title}")
        if confidence < 0.5:
            blockers.append(f"Low-confidence finding requires more evidence: {title}")
        if not observed:
            blockers.append(f"No directly observed supporting evidence is attached to: {title}")
        test_cases.append({
            "test_id": f"DL-UI-{index:03d}",
            "title": f"Regression check: {title}",
            "priority": severity if severity in {"low", "medium", "high", "critical"} else "normal",
            "preconditions": ["Use a controlled test build and synthetic or redacted data."],
            "steps": [
                "Reproduce the reported issue at the same browser and viewport.",
                "Capture the current screenshot and relevant console/network signals.",
                "Change only the suspected cause or apply the reviewed fix.",
                "Repeat the exact steps and compare the result with the baseline.",
            ],
            "expected_result": "The reported defect is absent and expected behaviour remains intact.",
            "status": "proposed_not_executed",
        })

    provider = str(analysis.get("provider") or "unknown")
    if provider == "mock":
        blockers.insert(0, "Mock mode does not inspect screenshot pixels; no visual diagnosis is available.")
    if not browser_evidence:
        blockers.append("Browser/runtime evidence has not been attached.")
    runtime_signals = {
        "console_error_count": len(browser_evidence.get("console_error_types", [])) if browser_evidence else 0,
        "page_error_count": len(browser_evidence.get("page_error_types", [])) if browser_evidence else 0,
        "failed_request_count": int(browser_evidence.get("failed_request_count", 0)) if browser_evidence else 0,
        "browser_evidence_attached": browser_evidence is not None,
    }
    hypotheses.sort(
        key=lambda item: (
            {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(item["severity"], 0),
            item["confidence"],
        ),
        reverse=True,
    )
    return {
        "pipeline_version": "deterministic-review-pipeline-1",
        "stages": [
            {"name": "perception_summary", "status": "completed", "note": "Summarises supplied findings; does not re-interpret pixels."},
            {"name": "evidence_correlation", "status": "completed" if browser_evidence else "waiting_for_browser_evidence"},
            {"name": "diagnosis_ranking", "status": "completed", "note": "Hypotheses remain unverified until a reviewer confirms them."},
            {"name": "test_planning", "status": "completed", "note": "Generated test cases are proposals and have not been executed."},
            {"name": "assurance_review", "status": "human_review_required"},
        ],
        "evidence_summary": {
            "finding_count": len(findings),
            "evidence_item_count": len(evidence_items),
            "directly_observed_evidence_count": sum(1 for item in evidence_items if item["observed"]),
            "runtime_signals": runtime_signals,
            "evidence": evidence_items,
        },
        "ranked_hypotheses": hypotheses,
        "test_cases": test_cases,
        "assurance": {
            "human_approval_required": True,
            "automatic_patch_execution": False,
            "automatic_merge_or_deploy": False,
            "blockers": list(dict.fromkeys(blockers)),
            "ready_for_patch_proposal": False,
        },
    }

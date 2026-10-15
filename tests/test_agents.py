from app.agents import build_investigation_pipeline


def test_pipeline_marks_mock_analysis_as_non_diagnostic() -> None:
    result = build_investigation_pipeline({
        "provider": "mock",
        "findings": [{
            "title": "Visual inspection required",
            "severity": "info",
            "confidence": 0.0,
            "evidence": [],
            "hypotheses": [],
        }],
    })
    assert result["assurance"]["human_approval_required"] is True
    assert result["assurance"]["automatic_patch_execution"] is False
    assert result["assurance"]["ready_for_patch_proposal"] is False
    assert any("Mock mode" in item for item in result["assurance"]["blockers"])
    assert result["test_cases"][0]["status"] == "proposed_not_executed"


def test_pipeline_ranks_high_severity_and_reports_runtime_evidence() -> None:
    result = build_investigation_pipeline(
        {
            "provider": "anthropic",
            "findings": [
                {
                    "title": "Button clipped",
                    "severity": "high",
                    "confidence": 0.82,
                    "evidence": [{"source": "screenshot", "description": "Button clipped", "observed": True}],
                    "hypotheses": ["Container overflow is likely"],
                },
                {
                    "title": "Text contrast",
                    "severity": "low",
                    "confidence": 0.4,
                    "evidence": [],
                    "hypotheses": ["Colour token may be incorrect"],
                },
            ],
        },
        {
            "console_error_types": ["error"],
            "page_error_types": [],
            "failed_request_count": 2,
        },
    )
    assert result["ranked_hypotheses"][0]["finding"] == "Button clipped"
    assert result["evidence_summary"]["runtime_signals"]["failed_request_count"] == 2
    assert any("High-impact" in item for item in result["assurance"]["blockers"])
    assert any("Low-confidence" in item for item in result["assurance"]["blockers"])
    assert result["stages"][-1]["status"] == "human_review_required"


def test_pipeline_handles_missing_findings_without_crashing() -> None:
    result = build_investigation_pipeline({"provider": "openai_compatible"})
    assert result["test_cases"] == []
    assert result["assurance"]["human_approval_required"] is True

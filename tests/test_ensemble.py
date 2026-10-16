from io import BytesIO

import pytest
from PIL import Image

from app.ensemble import compare_ensemble
from app.schemas import AnalysisResponse, Evidence, Finding, Severity


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (12, 12), "white").save(stream, format="PNG")
    return stream.getvalue()


def response(provider: str, findings: list[Finding]) -> AnalysisResponse:
    return AnalysisResponse(
        provider=provider,
        provider_version=f"{provider}-test",
        screenshot_sha256="a" * 64,
        screenshot_width=12,
        screenshot_height=12,
        bug_report="button alignment",
        findings=findings,
        test_plan=[],
        limitations=[],
    )


def finding(title: str, summary: str, category: str = "layout") -> Finding:
    return Finding(
        title=title,
        severity=Severity.MEDIUM,
        confidence=0.72,
        category=category,
        summary=summary,
        evidence=[Evidence(source="screenshot", description="Synthetic test evidence", observed=True)],
        hypotheses=["A CSS layout rule may be involved."],
        recommended_checks=["Compare a second viewport."],
    )


def test_ensemble_preserves_corroborated_and_minority_findings(monkeypatch) -> None:
    outputs = {
        "model_a": response("model_a", [
            finding("Primary button is clipped", "The primary button extends outside its container."),
            finding("Header text has low contrast", "Header text appears difficult to distinguish.", "accessibility"),
        ]),
        "model_b": response("model_b", [
            finding("Primary button clipped by container", "The primary button overflows the parent container.")
        ]),
    }

    def fake_analyse(image_bytes: bytes, bug_report: str | None, provider: str) -> AnalysisResponse:
        return outputs[provider]

    monkeypatch.setattr("app.ensemble.analyse_screenshot", fake_analyse)
    report = compare_ensemble(png_bytes(), "button alignment", ["model_a", "model_b"])
    assert report["providers_completed"] == 2
    assert len(report["finding_clusters"]) == 2
    corroborated = next(item for item in report["finding_clusters"] if item["supporting_provider_count"] == 2)
    assert corroborated["agreement_label"] == "cross-provider corroboration"
    assert report["unresolved_disagreement_count"] == 1
    assert report["assurance"]["minority_findings_preserved"] is True
    assert report["assurance"]["agreement_is_not_ground_truth"] is True


def test_ensemble_reports_provider_failure_without_claiming_no_findings(monkeypatch) -> None:
    def fake_analyse(image_bytes: bytes, bug_report: str | None, provider: str) -> AnalysisResponse:
        if provider == "down":
            raise RuntimeError("secret endpoint and token must not be returned")
        return response(provider, [finding("Button clipped", "Button extends beyond its container.")])

    monkeypatch.setattr("app.ensemble.analyse_screenshot", fake_analyse)
    report = compare_ensemble(png_bytes(), None, ["working", "down"])
    failed = next(item for item in report["provider_runs"] if item["provider"] == "down")
    assert failed["status"] == "failed"
    assert failed["error_code"] == "provider_unavailable"
    assert "secret" not in str(report)
    assert report["providers_failed"] == 1


@pytest.mark.parametrize("providers", [[], ["mock", "mock"], ["a", "b", "c", "d", "e"]])
def test_ensemble_rejects_invalid_provider_lists(providers: list[str]) -> None:
    with pytest.raises(ValueError):
        compare_ensemble(png_bytes(), None, providers)



def test_ensemble_distinguishes_privacy_consent_gate_from_provider_outage(monkeypatch) -> None:
    from app.services.analyzer import ProviderConsentRequired

    def fake_analyse(image_bytes: bytes, bug_report: str | None, provider: str) -> AnalysisResponse:
        if provider != "mock":
            raise ProviderConsentRequired("Do not leak this detailed message.")
        return response(provider, [])

    monkeypatch.setattr("app.ensemble.analyse_screenshot", fake_analyse)
    report = compare_ensemble(png_bytes(), None, ["mock", "anthropic"])
    failed = next(item for item in report["provider_runs"] if item["provider"] == "anthropic")
    assert failed["error_code"] == "provider_consent_required"
    assert "leak" not in str(report)

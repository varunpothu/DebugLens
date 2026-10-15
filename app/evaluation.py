"""Side-by-side provider evaluation without persisting screenshot bytes or raw model output."""
from dataclasses import asdict, dataclass
from time import perf_counter

from app.services.analyzer import analyse_screenshot


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    provider: str
    status: str
    latency_ms: float
    finding_count: int
    finding_titles: list[str]
    severities: list[str]
    confidence_values: list[float]
    model_version: str | None
    error_code: str | None = None


def compare_models(
    image_bytes: bytes,
    bug_report: str | None,
    providers: list[str],
) -> dict[str, object]:
    """Evaluate configured providers serially; failures are data, not silent fallbacks."""
    if not providers:
        raise ValueError("Select at least one provider.")
    if len(set(providers)) != len(providers):
        raise ValueError("Provider names must be unique in a comparison.")
    results: list[ModelEvaluation] = []
    for provider in providers:
        started = perf_counter()
        try:
            response = analyse_screenshot(image_bytes, bug_report, provider)
            results.append(
                ModelEvaluation(
                    provider=provider,
                    status="completed",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    finding_count=len(response.findings),
                    finding_titles=[item.title for item in response.findings],
                    severities=[item.severity.value for item in response.findings],
                    confidence_values=[item.confidence for item in response.findings],
                    model_version=response.provider_version,
                )
            )
        except Exception as exc:
            # Do not expose provider messages, request URLs, or credentials in evaluation reports.
            code = "provider_unavailable" if isinstance(exc, RuntimeError) else "evaluation_failed"
            results.append(
                ModelEvaluation(
                    provider=provider,
                    status="failed",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    finding_count=0,
                    finding_titles=[],
                    severities=[],
                    confidence_values=[],
                    model_version=None,
                    error_code=code,
                )
            )
    completed = [item for item in results if item.status == "completed"]
    return {
        "results": [asdict(item) for item in results],
        "completed_count": len(completed),
        "failed_count": len(results) - len(completed),
        "note": (
            "This harness compares outputs and latency; it does not determine which model is correct. "
            "Use a labelled benchmark and human adjudication to measure accuracy."
        ),
    }

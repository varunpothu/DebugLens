from io import BytesIO

import pytest
from PIL import Image

from app.config import Settings
from app.providers.base import ProviderResult
from app.providers.budget import ProviderCallBudget, ProviderRateLimitError
from app.schemas import Evidence, Finding, Severity
from app.services import analyzer


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (12, 12), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_provider_budget_is_independent_per_provider_and_returns_retry_window() -> None:
    budget = ProviderCallBudget(max_requests=1, window_seconds=60)
    budget.check("openai_compatible")
    budget.check("anthropic")

    with pytest.raises(ProviderRateLimitError) as raised:
        budget.check("openai_compatible")

    assert raised.value.provider == "openai_compatible"
    assert 1 <= raised.value.retry_after_seconds <= 60


def test_analysis_response_preserves_provider_token_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        analyzer,
        "get_settings",
        lambda: Settings(allow_unredacted_screenshots=True),
    )
    finding = Finding(
        title="Example issue",
        severity=Severity.LOW,
        confidence=0.7,
        category="layout",
        summary="A control appears misaligned.",
        evidence=[Evidence(source="screenshot", description="Visible misalignment.", observed=True)],
    )
    monkeypatch.setattr(
        analyzer,
        "_run_vision_provider",
        lambda *args, **kwargs: ProviderResult(
            provider="openai_compatible",
            model="example-model",
            findings=[finding],
            usage_input_tokens=123,
            usage_output_tokens=45,
        ),
    )

    response = analyzer.analyse_screenshot(png_bytes(), "Check alignment", "openai_compatible")

    assert response.usage_input_tokens == 123
    assert response.usage_output_tokens == 45
    assert response.provider_version == "example-model"


def test_mock_analysis_has_no_claimed_provider_usage() -> None:
    response = analyzer.analyse_screenshot(png_bytes(), "Synthetic fixture", "mock")

    assert response.usage_input_tokens is None
    assert response.usage_output_tokens is None

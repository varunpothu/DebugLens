from io import BytesIO

import pytest
from PIL import Image

from app.config import Settings
from app.services.analyzer import InvalidImageError, ProviderConsentRequired, analyse_screenshot, inspect_image


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 24), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_inspect_image_returns_digest_dimensions_and_mime() -> None:
    digest, width, height, media_type = inspect_image(png_bytes())
    assert len(digest) == 64
    assert width == 32
    assert height == 24
    assert media_type == "image/png"


def test_mock_analysis_is_explicit_about_limitations() -> None:
    result = analyse_screenshot(png_bytes(), "Button overlaps footer")
    assert result.provider == "mock"
    assert result.bug_report == "Button overlaps footer"
    assert result.human_review_required is True
    assert any("does not perform visual reasoning" in item for item in result.limitations)
    assert result.findings[0].confidence == 0.0


def test_invalid_bytes_are_rejected() -> None:
    with pytest.raises(InvalidImageError):
        inspect_image(b"not an image")


def test_empty_bytes_are_rejected() -> None:
    with pytest.raises(InvalidImageError):
        inspect_image(b"")


def test_unsupported_gif_is_rejected() -> None:
    stream = BytesIO()
    Image.new("RGB", (2, 2), "white").save(stream, format="GIF")
    with pytest.raises(InvalidImageError):
        inspect_image(stream.getvalue())


def test_external_provider_requires_explicit_screenshot_transfer_opt_in(monkeypatch) -> None:
    from app.services import analyzer

    monkeypatch.setattr(analyzer, "get_settings", lambda: Settings(allow_unredacted_screenshots=False))
    monkeypatch.setattr(
        analyzer,
        "_run_vision_provider",
        lambda *args, **kwargs: pytest.fail("provider must not receive image bytes without explicit opt-in"),
    )
    with pytest.raises(ProviderConsentRequired, match="screenshot pixels are not currently redacted"):
        analyse_screenshot(png_bytes(), "Test issue", provider="openai_compatible")


def test_analysis_exposes_provider_usage_metadata(monkeypatch) -> None:
    from app.services import analyzer

    from app.config import Settings
    from app.providers.base import ProviderResult

    monkeypatch.setattr(analyzer, "get_settings", lambda: Settings(allow_unredacted_screenshots=True))
    monkeypatch.setattr(
        analyzer,
        "_run_vision_provider",
        lambda *args, **kwargs: ProviderResult(
            provider="openai_compatible",
            model="test-vision-model",
            findings=[],
            raw_response_id="response-test-123",
            usage_input_tokens=321,
            usage_output_tokens=45,
            prompt_version="ui-investigator-v1",
        ),
    )

    result = analyse_screenshot(png_bytes(), "Synthetic test", provider="openai_compatible")

    assert result.provider_response_id == "response-test-123"
    assert result.provider_usage_input_tokens == 321
    assert result.provider_usage_output_tokens == 45
    assert result.prompt_version == "ui-investigator-v1"


def test_mock_analysis_has_no_provider_usage_metadata() -> None:
    result = analyse_screenshot(png_bytes(), "Synthetic test")

    assert result.provider_response_id is None
    assert result.provider_usage_input_tokens is None
    assert result.provider_usage_output_tokens is None
    assert result.prompt_version == "mock-baseline-1"

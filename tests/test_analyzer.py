from io import BytesIO

from PIL import Image
import pytest

from app.services.analyzer import InvalidImageError, analyse_screenshot, inspect_image


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 24), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_inspect_image_returns_digest_and_dimensions() -> None:
    digest, width, height = inspect_image(png_bytes())
    assert len(digest) == 64
    assert width == 32
    assert height == 24


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

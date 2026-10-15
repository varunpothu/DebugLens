from io import BytesIO

import pytest
from PIL import Image

from app.evaluation import compare_models


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (8, 8), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_comparison_reports_mock_and_unconfigured_provider() -> None:
    report = compare_models(png_bytes(), "Button misaligned", ["mock", "not-configured"])
    assert report["completed_count"] == 1
    assert report["failed_count"] == 1
    results = report["results"]
    assert results[0]["status"] == "completed"
    assert results[1]["status"] == "failed"
    assert results[1]["error_code"] == "provider_unavailable"


def test_comparison_requires_provider_list() -> None:
    with pytest.raises(ValueError, match="at least one"):
        compare_models(png_bytes(), None, [])


def test_comparison_rejects_duplicate_providers() -> None:
    with pytest.raises(ValueError, match="unique"):
        compare_models(png_bytes(), None, ["mock", "mock"])

from io import BytesIO

import pytest
from PIL import Image

from app.visual_regression import (
    VisualRegressionInputError,
    compare_screenshots,
)


def png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_identical_screenshots_have_zero_difference() -> None:
    screenshot = png_bytes(Image.new("RGB", (20, 10), "white"))
    report = compare_screenshots(screenshot, screenshot)
    assert report.status == "compared"
    assert report.changed_pixels == 0
    assert report.changed_ratio == 0.0
    assert report.mean_absolute_error == 0.0
    assert report.within_threshold is True
    assert report.difference_bounds is None


def test_small_change_reports_ratio_and_bounding_box() -> None:
    baseline = Image.new("RGB", (10, 10), "white")
    current = baseline.copy()
    current.putpixel((2, 3), (0, 0, 0))
    report = compare_screenshots(
        png_bytes(baseline),
        png_bytes(current),
        pixel_threshold=12,
        max_changed_ratio=0.02,
    )
    assert report.changed_pixels == 1
    assert report.total_pixels == 100
    assert report.changed_ratio == 0.01
    assert report.difference_bounds == (2, 3, 3, 4)
    assert report.within_threshold is True
    assert report.to_dict()["difference_bounds"] == [2, 3, 3, 4]


def test_dimension_mismatch_fails_closed() -> None:
    baseline = png_bytes(Image.new("RGB", (10, 10), "white"))
    current = png_bytes(Image.new("RGB", (11, 10), "white"))
    report = compare_screenshots(baseline, current)
    assert report.status == "dimension_mismatch"
    assert report.within_threshold is False
    assert report.changed_ratio is None


@pytest.mark.parametrize(
    ("pixel_threshold", "max_changed_ratio"),
    [(-1, 0.1), (256, 0.1), (1, -0.1), (1, 1.1)],
)
def test_invalid_thresholds_are_rejected(pixel_threshold: int, max_changed_ratio: float) -> None:
    image = png_bytes(Image.new("RGB", (1, 1), "white"))
    with pytest.raises(ValueError):
        compare_screenshots(
            image,
            image,
            pixel_threshold=pixel_threshold,
            max_changed_ratio=max_changed_ratio,
        )


def test_invalid_and_oversized_images_are_rejected() -> None:
    with pytest.raises(VisualRegressionInputError, match="valid supported image"):
        compare_screenshots(b"not an image", b"not an image")
    with pytest.raises(VisualRegressionInputError, match="1 to 25 MiB"):
        compare_screenshots(b"", b"")

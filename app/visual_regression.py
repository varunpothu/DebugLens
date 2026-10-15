"""Deterministic screenshot comparison utilities for visual regression checks.

The metric is intentionally transparent and local-only. It is a regression signal, not a
substitute for human review or a perceptual model; dynamic regions must be masked upstream.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO

from PIL import Image, ImageChops, ImageStat, UnidentifiedImageError

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


class VisualRegressionInputError(ValueError):
    """Raised when a screenshot is invalid or exceeds comparison bounds."""


@dataclass(frozen=True, slots=True)
class VisualRegressionReport:
    status: str
    baseline_width: int
    baseline_height: int
    current_width: int
    current_height: int
    changed_pixels: int | None
    total_pixels: int | None
    changed_ratio: float | None
    mean_absolute_error: float | None
    pixel_threshold: int
    max_changed_ratio: float
    within_threshold: bool
    difference_bounds: tuple[int, int, int, int] | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible report with the bounding box as a list."""
        result = asdict(self)
        if self.difference_bounds is not None:
            result["difference_bounds"] = list(self.difference_bounds)
        return result


def _decode_screenshot(content: bytes) -> Image.Image:
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise VisualRegressionInputError("Screenshot must contain 1 to 25 MiB of image data.")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise VisualRegressionInputError("Only PNG, JPEG, and WEBP screenshots are supported.")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise VisualRegressionInputError("Screenshot dimensions exceed the 40-million-pixel limit.")
            image.load()
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise VisualRegressionInputError("Screenshot bytes are not a valid supported image.") from exc


def compare_screenshots(
    baseline_bytes: bytes,
    current_bytes: bytes,
    *,
    pixel_threshold: int = 12,
    max_changed_ratio: float = 0.005,
) -> VisualRegressionReport:
    """Compare same-sized screenshots and report changed-pixel ratio and MAE.

    A pixel counts as changed when its maximum per-channel absolute difference is greater than
    pixel_threshold. The changed ratio is the fraction of such pixels. The mean absolute error
    is the average absolute channel difference normalised to 0..1. Dimension mismatch is always
    outside threshold because alignment would otherwise be ambiguous.
    """
    if not 0 <= pixel_threshold <= 255:
        raise ValueError("pixel_threshold must be between 0 and 255.")
    if not 0.0 <= max_changed_ratio <= 1.0:
        raise ValueError("max_changed_ratio must be between 0 and 1.")
    baseline = _decode_screenshot(baseline_bytes)
    current = _decode_screenshot(current_bytes)
    baseline_width, baseline_height = baseline.size
    current_width, current_height = current.size
    if baseline.size != current.size:
        return VisualRegressionReport(
            status="dimension_mismatch",
            baseline_width=baseline_width,
            baseline_height=baseline_height,
            current_width=current_width,
            current_height=current_height,
            changed_pixels=None,
            total_pixels=None,
            changed_ratio=None,
            mean_absolute_error=None,
            pixel_threshold=pixel_threshold,
            max_changed_ratio=max_changed_ratio,
            within_threshold=False,
            difference_bounds=None,
        )
    difference = ImageChops.difference(baseline, current)
    channels = difference.split()
    maximum_channel_difference = ImageChops.lighter(
        ImageChops.lighter(channels[0], channels[1]), channels[2]
    )
    changed_mask = maximum_channel_difference.point(
        lambda value: 255 if value > pixel_threshold else 0
    )
    changed_pixels = changed_mask.histogram()[255]
    total_pixels = baseline_width * baseline_height
    changed_ratio = changed_pixels / total_pixels
    mean_absolute_error = sum(ImageStat.Stat(difference).mean) / (3 * 255)
    return VisualRegressionReport(
        status="compared",
        baseline_width=baseline_width,
        baseline_height=baseline_height,
        current_width=current_width,
        current_height=current_height,
        changed_pixels=changed_pixels,
        total_pixels=total_pixels,
        changed_ratio=changed_ratio,
        mean_absolute_error=mean_absolute_error,
        pixel_threshold=pixel_threshold,
        max_changed_ratio=max_changed_ratio,
        within_threshold=changed_ratio <= max_changed_ratio,
        difference_bounds=changed_mask.getbbox(),
    )

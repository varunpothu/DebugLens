"""Deterministic screenshot comparison utilities for visual regression checks.

The metric is intentionally transparent and local-only. It is a regression signal, not a
substitute for human review or a perceptual model; dynamic regions must be masked upstream.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageStat, UnidentifiedImageError

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
    perceptual_hash_distance: float | None
    masked_pixels: int
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


def _difference_hash(image: Image.Image) -> int:
    """Return a compact 64-bit difference hash for perceptual-change signalling."""
    grayscale = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(grayscale.getdata())
    result = 0
    for row in range(8):
        for column in range(8):
            if pixels[row * 9 + column] > pixels[row * 9 + column + 1]:
                result |= 1 << (row * 8 + column)
    return result


def compare_screenshots(
    baseline_bytes: bytes,
    current_bytes: bytes,
    *,
    pixel_threshold: int = 12,
    max_changed_ratio: float = 0.005,
    mask_regions: list[tuple[int, int, int, int]] | None = None,
) -> VisualRegressionReport:
    """Compare same-sized screenshots and report changed-pixel ratio and MAE.

    A pixel counts as changed when its maximum per-channel absolute difference is greater than
    pixel_threshold. The changed ratio is the fraction of such pixels. The mean absolute error
    is the average absolute channel difference normalised to 0..1. A difference-hash distance
    adds a coarse perceptual signal; it is not a learned metric or a correctness guarantee.
    Optional mask rectangles use (left, top, right, bottom) coordinates and exclude dynamic
    regions from pixel metrics. Dimension mismatch is always outside threshold.
    """
    if not 0 <= pixel_threshold <= 255:
        raise ValueError("pixel_threshold must be between 0 and 255.")
    if not 0.0 <= max_changed_ratio <= 1.0:
        raise ValueError("max_changed_ratio must be between 0 and 1.")
    regions = mask_regions or []
    if len(regions) > 100:
        raise ValueError("At most 100 dynamic regions may be masked.")
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
            perceptual_hash_distance=None,
            masked_pixels=0,
            pixel_threshold=pixel_threshold,
            max_changed_ratio=max_changed_ratio,
            within_threshold=False,
            difference_bounds=None,
        )
    comparison_mask = Image.new("L", baseline.size, 255)
    draw = ImageDraw.Draw(comparison_mask)
    for region in regions:
        if len(region) != 4 or any(not isinstance(value, int) for value in region):
            raise ValueError("Each mask region must contain four integer coordinates.")
        left, top, right, bottom = region
        if not (0 <= left < right <= baseline_width and 0 <= top < bottom <= baseline_height):
            raise ValueError("Mask regions must be non-empty and lie within the screenshot.")
        draw.rectangle((left, top, right - 1, bottom - 1), fill=0)

    masked_pixels = comparison_mask.histogram()[0]
    compared_pixels = baseline_width * baseline_height - masked_pixels
    if compared_pixels < 1:
        raise ValueError("Mask regions must leave at least one pixel available for comparison.")

    difference = ImageChops.difference(baseline, current)
    channels = difference.split()
    maximum_channel_difference = ImageChops.lighter(
        ImageChops.lighter(channels[0], channels[1]), channels[2]
    )
    changed_mask = maximum_channel_difference.point(
        lambda value: 255 if value > pixel_threshold else 0
    )
    changed_mask = ImageChops.multiply(changed_mask, comparison_mask)
    changed_pixels = changed_mask.histogram()[255]
    changed_ratio = changed_pixels / compared_pixels
    mean_absolute_error = sum(
        sum(ImageStat.Stat(channel, mask=comparison_mask).mean) for channel in channels
    ) / (3 * 255)

    current_for_hash = current.copy()
    current_for_hash.paste(baseline, (0, 0), ImageChops.invert(comparison_mask))
    hash_distance = (_difference_hash(baseline) ^ _difference_hash(current_for_hash)).bit_count() / 64
    return VisualRegressionReport(
        status="compared",
        baseline_width=baseline_width,
        baseline_height=baseline_height,
        current_width=current_width,
        current_height=current_height,
        changed_pixels=changed_pixels,
        total_pixels=compared_pixels,
        changed_ratio=changed_ratio,
        mean_absolute_error=mean_absolute_error,
        perceptual_hash_distance=hash_distance,
        masked_pixels=masked_pixels,
        pixel_threshold=pixel_threshold,
        max_changed_ratio=max_changed_ratio,
        within_threshold=changed_ratio <= max_changed_ratio,
        difference_bounds=changed_mask.getbbox(),
    )

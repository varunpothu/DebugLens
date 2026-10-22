# Visual regression checks

DebugLens provides a local, deterministic visual-comparison utility in `app.visual_regression`. It compares PNG, JPEG, or WEBP screenshots without sending them to a model provider.

## Example

```python
from pathlib import Path

from app.visual_regression import compare_screenshots

report = compare_screenshots(
    Path("baseline.png").read_bytes(),
    Path("current.png").read_bytes(),
    pixel_threshold=12,
    max_changed_ratio=0.005,
    mask_regions=[(0, 0, 160, 40)],  # (left, top, right, bottom)
)

print(report.to_dict())
if not report.within_threshold:
    raise SystemExit("Visual regression needs review")
```

## Metrics

- `changed_pixels`: compared pixels where the maximum absolute RGB channel difference exceeds `pixel_threshold`.
- `total_pixels`: pixels included in comparison after excluding masked regions.
- `masked_pixels`: pixels excluded by dynamic-region masks.
- `changed_ratio`: changed pixels divided by the compared pixel count.
- `mean_absolute_error`: average absolute RGB channel difference for compared pixels, normalised to 0..1.
- `perceptual_hash_distance`: normalised Hamming distance between 64-bit difference hashes, from 0 (same hash) to 1 (all bits differ). This is a coarse signal, not a learned perceptual model.
- `difference_bounds`: bounding box around changed pixels after masking, or null when no pixels exceed the threshold.
- `dimension_mismatch`: screenshots have different dimensions; this fails closed and does not attempt alignment.

Input is limited to 25 MiB and 40 million pixels per image. Up to 100 masks may be supplied as integer rectangles `(left, top, right, bottom)`; each must be non-empty and lie inside the screenshot, and the masks must leave at least one pixel to compare. Masked regions are replaced with baseline pixels for the hash calculation.

All metrics are local and deterministic. The hash does not understand layout semantics, and a passing ratio is not proof that a UI is correct. Dynamic timestamps, animations, cursors, and ads can cause noise; mask or stabilise only approved regions before comparison. Always review important visual changes and pair visual metrics with accessibility checks and functional tests.

# Visual regression checks

DebugLens provides a local, deterministic pixel-difference utility in `app.visual_regression`. It compares PNG, JPEG, or WEBP screenshots without sending them to a model provider.

## Example

```python
from pathlib import Path

from app.visual_regression import compare_screenshots

report = compare_screenshots(
    Path("baseline.png").read_bytes(),
    Path("current.png").read_bytes(),
    pixel_threshold=12,
    max_changed_ratio=0.005,
)

print(report.to_dict())
if not report.within_threshold:
    raise SystemExit("Visual regression needs review")
```

## Metrics

- `changed_pixels`: pixels where the maximum absolute RGB channel difference exceeds `pixel_threshold`.
- `changed_ratio`: changed pixels divided by the total pixel count.
- `mean_absolute_error`: average absolute RGB channel difference, normalised to 0..1.
- `difference_bounds`: bounding box around changed pixels, or null when no pixels exceed the threshold.
- `dimension_mismatch`: screenshots have different dimensions; this fails closed and does not attempt alignment.

Input is limited to 25 MiB and 40 million pixels per image. The threshold is deterministic, but it is not a perceptual model and does not understand layout semantics. Dynamic timestamps, animations, cursors, and ads can cause noise; mask or stabilise such regions before comparison. Always review important visual changes and pair pixel metrics with accessibility checks and functional tests. A passing ratio is not proof that a UI is correct.

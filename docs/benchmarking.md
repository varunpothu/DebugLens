# Labelled screenshot benchmark

The benchmark runner evaluates category-level defect detection against a versioned JSON manifest. It reports per-category precision, recall, F1, macro F1, exact category-set matches, and provider failures. It does not claim localisation accuracy, evidence quality, or root-cause correctness.

## Manifest format

Place the manifest and images in a dedicated directory. Use only synthetic, redacted, consented fixtures.

~~~json
{
  "schema_version": 1,
  "dataset_version": "synthetic-ui-v1",
  "cases": [
    {
      "id": "button-overflow-mobile",
      "image": "fixtures/button-overflow-mobile.png",
      "bug_report": "Primary button overflows at a narrow viewport",
      "expected_categories": ["layout"]
    },
    {
      "id": "missing-label",
      "image": "fixtures/missing-label.png",
      "bug_report": "A form field is not announced correctly",
      "expected_categories": ["accessibility"]
    }
  ]
}
~~~

Paths must remain inside the manifest directory. Symlinked files, absolute paths, traversal, duplicate case IDs, malformed manifests, and images larger than 10 MiB are rejected.

## Run

~~~powershell
python -m app.benchmark .\benchmarks\manifest.json --provider mock --output .\benchmark-report.json
~~~

Mock mode is intentionally rejected for benchmark scoring because it does not inspect screenshot pixels. Use a configured real vision provider only after reviewing the screenshot-transfer consent gate and provider data-processing terms. Keep API keys in the environment, never in the manifest.

## Interpreting the report

- Precision estimates the share of predicted categories that are present in the labels.
- Recall estimates the share of labelled categories that the model found.
- F1 is the harmonic mean of precision and recall.
- Macro F1 weights each category equally, which helps expose weak performance on less common classes.
- A provider failure counts expected categories as missed and is reported separately. A failure must never be interpreted as a clean screenshot.

These metrics are only as reliable as the labels and dataset. Split by application/repository, include clean controls and ambiguous cases, blind human reviewers to provider identity where possible, report sample sizes and uncertainty, and maintain an independent adjudication process. Never use model agreement alone as ground truth.

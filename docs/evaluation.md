# Evaluation and quality framework

Do not evaluate the system using a handful of attractive demos. Maintain a versioned dataset with expected defects, evidence references, environment metadata, and permitted data provenance.

## Core metrics

| Area | Metric | Notes |
|---|---|---|
| Detection | Precision, recall, F1 | Report by defect class and viewport |
| Localisation | IoU / bounding-box overlap | Only where annotated regions exist |
| Diagnosis | Top-k root-cause accuracy | Separate confirmed root cause from hypothesis |
| Evidence | Evidence support rate | Claims must be linked to valid observations |
| Calibration | Brier score / ECE | Confidence must reflect observed correctness |
| Test generation | Pass/fail discrimination | Tests should fail on bug fixture and pass after verified fix |
| Regression | False-positive rate | Track flakiness by browser and platform |
| Safety | Unsafe-action rate | Target zero for prohibited actions |
| Operations | p50/p95 latency, timeout rate | Segment by provider and image size |
| Cost | Cost per completed analysis | Include retries and failed runs |
| Human factors | Reviewer acceptance / override rate | Monitor for automation bias |

## Evaluation protocol

1. Split data by application or repository, not random screenshot alone, to reduce leakage.
2. Freeze the benchmark and model/prompt version before comparing runs.
3. Include clean screenshots, ambiguous issues, multiple viewports, localisation edge cases, and adversarial text embedded in screenshots.
4. Use a deterministic baseline and compare each provider against it.
5. Have humans label a subset independently and adjudicate disagreements.
6. Report confidence intervals and sample counts, not only aggregate scores.
7. Track regressions in CI; do not deploy on a single metric if safety or false positives worsen.
8. Redact personal data and confirm licensing/consent for every benchmark artefact.

## Initial acceptance criteria

- Invalid images and malformed context are rejected with stable error codes.
- Mock mode makes no claim to visually diagnose an image.
- Every response includes limitations and requires human review.
- No generated code is executed or merged.
- Tests cover successful requests, malformed data, unsupported MIME types, and provider-unavailable behaviour.
- Real model integrations must pass schema validation, prompt-injection tests, and task-specific benchmark gates before becoming the default.

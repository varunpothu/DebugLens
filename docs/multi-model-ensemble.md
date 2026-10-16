# Multi-model ensemble and disagreement analysis

DebugLens can compare up to four explicitly selected providers on the same validated screenshot and issue report. Each provider's findings are preserved, and a heuristic clusters findings that appear semantically similar by category, title, and summary.

## What the report means

- **Cross-provider corroboration** means two or more selected providers produced similar findings. It is not proof of correctness.
- **Single-provider signal** means only one provider produced a finding in that cluster. It may be valid and must not be discarded as an outlier.
- **Provider failure** is reported separately and must never be interpreted as zero findings.
- Confidence values are retained per model. They are not averaged because provider confidence scales are not known to be calibrated against each other.
- Semantic clustering is heuristic. Reviewers should inspect original finding text and evidence before using a cluster to prioritise work.

## API

POST /v1/ensemble-analyses accepts a multipart screenshot, optional bug_report, and a comma-separated providers field. The maximum is four providers per request to limit latency and cost. Use the same synthetic fixture and report across models when comparing behaviour.

Example:

~~~powershell
curl.exe -X POST http://127.0.0.1:8000/v1/ensemble-analyses -F "screenshot=@sample.png" -F "bug_report=The primary button is clipped on mobile" -F "providers=mock,openai_compatible,anthropic"
~~~

Real providers are still subject to the existing screenshot-transfer consent gate. The endpoint does not silently fall back to a different model. It returns per-provider failures without exposing raw provider error text.

## Evaluation guidance

Use a versioned labelled benchmark, hold out repositories or applications to avoid leakage, blind reviewers to provider identity where practical, and report precision, recall, localisation quality, false positives, confidence calibration, latency, and cost. Do not use cross-model agreement as a proxy for ground truth.

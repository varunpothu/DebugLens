# Multi-model evaluation

DebugLens supports explicit provider selection for OpenAI-compatible vision endpoints, Anthropic, and Gemini. The comparison harness runs selected providers sequentially and records latency, result status, finding count, severity, confidence, and model version. It deliberately does not persist screenshot bytes or raw model responses in the report.

## How to use

The Python API is:

~~~python
from app.evaluation import compare_models

with open("redacted-ui.png", "rb") as handle:
    report = compare_models(
        handle.read(),
        "The modal overlaps the primary button on a narrow viewport",
        ["mock", "openai_compatible", "anthropic", "gemini"],
    )
~~~

Configure credentials for every real provider you select. A provider that is not configured is reported as failed; the harness never silently substitutes another model.

## Correctness methodology

- Use a labelled dataset with expected defect classes and annotated evidence.
- Split by application/repository, not random screenshots, to reduce leakage.
- Compare precision, recall, localisation quality, root-cause accuracy, evidence support, confidence calibration, false positives, latency, and cost.
- Treat model agreement as a signal, not proof. Multiple models can share the same failure mode.
- Blind human reviewers to model identity for a portion of the evaluation and adjudicate disagreements.
- Include clean controls, ambiguous cases, different viewports, and prompt-injection strings rendered inside screenshots.
- Do not send sensitive screenshots to external providers without explicit approval and a reviewed data-processing basis.

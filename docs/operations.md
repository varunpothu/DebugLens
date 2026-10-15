# Operations guide

## Local development

Use Python 3.11 or 3.12, create a virtual environment, install the dev extra, and run pytest, Ruff and mypy before opening a pull request.

## Failure handling

- Invalid upload: return 415, 413 or 422; do not retry.
- Invalid context: return 400; correct the request.
- Provider unavailable: return 503 without exposing credential or provider internals.
- Timeout: mark the workflow failed or retry only within a configured budget.
- Test failure: preserve the failure result; never convert it into success after a retry without recording the earlier failure.
- Suspected sensitive data: stop external processing, restrict access, follow the organisation's incident and deletion process.

## Production signals

Monitor request count, rejection rate, p50/p95 latency, provider error/timeout rate, queue depth, dead-letter count, analysis completion rate, token/cost budget, test flakiness, human override rate, and unsafe-action attempts.

## Incident response checklist

1. Disable the affected provider or workflow capability using configuration/feature flags.
2. Preserve redacted logs and correlation IDs; avoid copying raw screenshots into tickets.
3. Determine affected tenants, artefacts, model/provider versions, and time window.
4. Revoke exposed credentials and rotate secrets if needed.
5. Delete affected artefacts according to policy and legal requirements.
6. Document root cause, impact, remediation, and regression tests.
7. Re-enable only after the relevant release gate passes.

# Threat model and assurance controls

## Assets

Screenshots, source snippets, DOM and HAR data, provider credentials, repository contents, generated patches, audit records, and cloud credentials.

## Trust boundaries

1. User upload to API.
2. API to external model provider.
3. Model output to orchestrator.
4. Orchestrator to browser/test worker.
5. Generated patch to repository.
6. CI identity to cloud deployment.

## Key threats and mitigations

- **Malicious upload / parser abuse:** byte limits, MIME allow-list plus actual image decoding, pixel limits, dependency updates, isolated processing.
- **Prompt injection in screenshots, DOM, logs or source:** treat all artefacts as untrusted data; never allow artefact text to change system policy, tools, credentials, or approval requirements.
- **Sensitive data exfiltration:** synthetic fixtures by default, redaction before provider calls, provider data-processing review, no raw artefacts in logs, retention limits.
- **Hallucinated diagnosis:** typed output schema, evidence references, explicit hypotheses, confidence calibration, human review.
- **Unsafe generated patch:** diff-only proposal, protected branches, CI gates, no host execution, sandboxed test environment, explicit approval.
- **SSRF and browser pivoting:** deny arbitrary URLs, enforce domain allow-list, block private/link-local/metadata IP ranges, egress filtering, DNS rebinding protection, no ambient credentials.
- **Supply-chain compromise:** pinned or bounded dependencies, lockfile in release process, dependency and secret scanning, signed artefacts where practical.
- **Denial of service / cost abuse:** upload and pixel limits, request rate limits at gateway, per-run timeouts, concurrency and token budgets, quotas.
- **Audit leakage:** structured redacted logs; avoid screenshot content, auth headers, query secrets and raw prompts in logs.
- **Cross-tenant leakage:** tenant-scoped authorisation and object paths before any multi-user deployment.

## Safety invariants

- The system never deploys or merges a generated fix automatically.
- A failed or timed-out test is not a pass.
- A model claim is not evidence that an action occurred.
- External browsing and code execution are disabled unless the operator enables narrowly scoped capabilities.
- Human approval is explicit, attributable, and tied to the exact patch digest and test results.
- Deletion and retention policies apply to raw artefacts as well as derived data.

## Release gates

Before production: independent security review, threat-model sign-off, upload fuzzing, dependency scan, secret scan, abuse/rate-limit tests, red-team prompt injection tests, provider privacy review, disaster recovery rehearsal, and incident response runbook.

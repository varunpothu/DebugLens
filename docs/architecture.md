# Architecture

## Design goals

1. Keep ingestion, orchestration, model adapters, and evidence contracts independently testable.
2. Make every claim distinguish observed evidence from inference.
3. Treat the model as a fallible component and untrusted input/output boundary.
4. Require approval before applying patches, opening network access, or changing external systems.
5. Preserve enough metadata to reproduce evaluations without retaining sensitive screenshots indefinitely.

## Components

- **API ingress:** validates content type, upload size, context shape, and returns a correlation ID.
- **Evidence normaliser:** validates image bytes, computes a content digest and records dimensions. Automatic PII redaction is not implemented yet.
- **Analysis orchestrator:** calls the explicitly configured provider and returns typed findings, test suggestions, and limitations. It does not infer runtime facts from screenshots alone.
- **Vision adapters:** OpenAI-compatible, Anthropic, and Gemini adapters behind a shared provider contract.
- **Local run store:** SQLite persistence for analysis output, workflow state, and actor-attributed audit events. Use PostgreSQL and schema migrations for multi-user production.
- **Browser evidence collector:** optional Playwright capture behind a disabled-by-default endpoint. It captures screenshot analysis, page title, viewport, tag counts, console error types, page error classes, and failed-request counts. Exact hostname allow-listing is necessary but not sufficient without network egress controls.
- **Model comparison harness:** records provider output summaries and latency. Correctness requires a labelled benchmark and human adjudication.
- **Streamlit dashboard:** create investigations, browse history, inspect findings, and record legal workflow transitions.
- **Repair proposer (planned):** emits a diff and rationale. It must not execute or merge the diff.
- **Verifier (planned):** runs tests and visual comparisons in an isolated worker and records both passing and failing checks.

## State machine

RECEIVED -> VALIDATED -> EVIDENCE_COLLECTED -> HYPOTHESES_READY -> HUMAN_REVIEW -> REPRODUCED -> PATCH_PROPOSED -> TESTED -> VERIFIED or REJECTED.

Any eligible state may transition to FAILED or CANCELLED according to the explicit transition map. A timeout must not silently advance a workflow. Human state changes require actor and reason fields.

## Data retention

The run store retains screenshot SHA-256 digests and structured analysis, not original uploaded screenshot bytes. Browser screenshot bytes are analysed in memory and are not retained by the run store. Provider calls still transmit screenshots to the configured external provider when a real provider is enabled. Review provider privacy, retention, residency, and contractual terms before sending sensitive material.

## Security boundary

The API currently has no authentication, authorisation, rate limiting, or tenant isolation. Keep it local or inside a trusted development environment. The browser endpoint is disabled by default and must only be enabled in a disposable worker with exact host allow-lists and network-level SSRF/egress controls. Do not treat application-level URL checks as a substitute for firewall rules.

## Production deployment target

Recommended AWS path after local validation:

- Amazon ECS Fargate for API and isolated worker tasks.
- Application Load Balancer with TLS, authentication, and request limits.
- S3 with SSE-KMS, short lifecycle, and narrowly scoped access for approved artefacts.
- SQS for asynchronous jobs and DLQs for repeated failures.
- Step Functions for durable workflows and explicit human approval callbacks.
- Secrets Manager for provider credentials.
- CloudWatch logs/metrics/alarms and OpenTelemetry-compatible traces.
- ECR image scanning and GitHub Actions OIDC for deployment without long-lived AWS keys.

Do not deploy Terraform until account, region, budgets, retention, networking, IAM, and threat model are reviewed. The current Terraform module provisions only private artifact storage, not the application infrastructure.

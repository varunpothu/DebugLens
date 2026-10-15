# Architecture

## Design goals

1. Keep ingestion, orchestration, model adapters, and evidence contracts independently testable.
2. Make every claim distinguish observed evidence from inference.
3. Treat the model as a fallible component and untrusted input/output boundary.
4. Require approval before applying patches, opening network access, or changing external systems.
5. Preserve enough metadata to reproduce evaluations without retaining sensitive screenshots indefinitely.

## Components

- **API ingress:** validates content type, upload size, context shape, and returns a correlation ID.
- **Evidence normaliser:** computes a content digest and records dimensions. Future adapters should redact or minimise sensitive content before external transmission.
- **Analysis orchestrator:** coordinates bounded tasks, enforces timeouts and budgets, validates typed outputs, and records failures.
- **Vision adapter:** provider-specific implementation behind a stable interface. Provider choice must be explicit.
- **Browser evidence collector (planned):** Playwright-based screenshots, DOM snapshots, console errors, network failures, viewport and browser metadata. Run only against an allow-listed target in a disposable environment.
- **Test planner (planned):** converts supported findings into candidate test cases, never treats generated tests as authoritative until reviewed.
- **Repair proposer (planned):** emits a diff and rationale. It does not execute or merge the diff.
- **Verifier (planned):** runs tests and visual comparisons in an isolated worker and records both passing and failing checks.
- **Audit and observability:** correlation IDs, redacted structured events, latency, model version, prompt version, token/cost budget, and evaluation results.

## State machine

RECEIVED -> VALIDATED -> EVIDENCE_COLLECTED -> HYPOTHESES_READY -> HUMAN_REVIEW -> REPRODUCED -> PATCH_PROPOSED -> TESTED -> VERIFIED or REJECTED.

Any state may transition to FAILED or CANCELLED. Transitions should be explicit and idempotent. A timeout must not silently advance a workflow.

## Evidence contract

Each finding has a severity, calibrated confidence, category, explanation, supporting evidence, hypotheses, and recommended checks. Evidence records identify the source and whether it is directly observed. Future model adapters must not fabricate browser logs or claim a test was run when it was not.

## Production deployment target

Recommended AWS path after local validation:

- Amazon ECS Fargate for API and isolated worker tasks.
- Application Load Balancer with TLS and request limits.
- S3 with SSE-KMS, short lifecycle, and narrowly scoped access for approved artefacts.
- SQS for asynchronous jobs and DLQs for repeated failures.
- Step Functions for durable workflows and explicit human approval callbacks.
- Secrets Manager for provider credentials.
- CloudWatch logs/metrics/alarms and OpenTelemetry-compatible traces.
- ECR image scanning and GitHub Actions OIDC for deployment without long-lived AWS keys.

Do not deploy Terraform until account, region, budgets, retention, networking, IAM, and threat model are reviewed. Production infrastructure is not created by this scaffold.

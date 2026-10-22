# Roadmap

## Phase 0: Reliable foundation

- [x] Typed response contract and deterministic mock mode
- [x] FastAPI health/readiness and upload endpoint
- [x] Image decoding, MIME allow-list, upload size and pixel bounds
- [x] SQLite run persistence and audit trail for local workflows
- [x] API endpoints for creating runs, listing runs, reading a run, and recording legal transitions
- [x] Unit, API, workflow, model-evaluation, provider-contract, and target-validation tests
- [x] Threat model, architecture, evaluation criteria, and operations guidance
- [x] CI pipeline for Python 3.11/3.12, Ruff, pytest, mypy, isolated worker, and Terraform validation
- [x] Run CI, CodeQL, and dependency audit on pushes and pull requests targeting both `dev` and `main`
- [x] Add a bounded process-local rate limiter for write/analysis endpoints with `429` and `Retry-After` responses
- [x] Add a total request-size guard for `/v1/` write requests, including requests without a length header
- [ ] Configure distributed gateway rate limits, trusted proxy handling, and per-tenant/provider cost quotas before public deployment
- [x] Confirm CI, CodeQL, and dependency audit passed together on commit `6b794909145f306f632d98ad0dd11cee742960ad`; repeat checks against every release candidate.

## Phase 1: Multimodal analysis and model evaluation

- [x] Provider-neutral vision contract
- [x] Opt-in OpenAI-compatible, Anthropic, and Gemini adapters
- [x] Structured output validation and safe provider failure handling
- [x] Mocked HTTP contract tests for each provider
- [x] Side-by-side model comparison harness for latency and output summaries
- [x] Multi-model ensemble endpoint with heuristic finding clusters, provider failures, and preserved minority findings
- [x] Labelled screenshot benchmark runner with category precision, recall, F1, and safe fixture path validation
- [x] Deterministic evidence summary, hypothesis ranking, test-case proposal, and assurance blockers
- [ ] Populate a versioned, representative screenshot benchmark with human-adjudicated ground truth and held-out application splits
- [x] Add deterministic pattern-based text redaction before external provider calls (not screenshot OCR or comprehensive DLP)
- [x] Deny external vision-provider image transfer by default unless an operator explicitly opts in; this is a consent gate, not OCR/DLP.
- [ ] Add OCR-assisted screenshot redaction, adversarial obfuscation tests, and independent privacy review
- [x] Add process-local per-provider request budgets with 429/Retry-After responses; these are not distributed quotas.
- [ ] Add bounded retries, distributed provider quotas, persistent price-aware cost telemetry, and account-level budget enforcement
- [x] Return provider response IDs and input/output token counts when supplied by the provider
- [x] Version the vision prompt contract and expose its version in analysis responses; this is traceability metadata, not persistent prompt history

## Phase 2: Browser evidence

- [x] Initial Playwright capture library
- [x] Exact hostname allow-list and URL validation tests
- [x] Capture screenshot, page title, tag counts, console error types, and failed-request counts
- [x] Optional API integration that attaches minimised browser evidence to a durable run
- [ ] Run in a disposable container with network egress controls and DNS/SSRF protection
- [ ] Add resource quotas, cancellation, job timeouts, artifact expiry, and reproduction metadata

## Phase 3: Human-governed repair workflow

- [x] Explicit workflow state machine and audit events
- [x] Human review dashboard for run history and legal transitions
- [x] Human-authored and provider-assisted patch proposals with digest, rationale, risk, and rollback plan
- [x] Reviewer-reported test-result records tied to the exact patch digest
- [x] Gate verification on a passing signed execution report for the current patch digest
- [x] Record a verification audit event bound to the patch digest, trusted execution report ID, suite, and workspace digest
- [x] Add a standalone allowlisted test-worker with timeout, output cap, and workspace snapshot digest
- [x] Add a host-side Docker orchestrator and HMAC-signed execution-result API
- [x] Persist execution suite, exit code, workspace digest, duration, and bounded logs
- [x] Provision a reviewed single-file text patch into a disposable copy with base/patch/workspace digests and manifest verification
- [x] Verify the supplied full base commit SHA against Git HEAD and reject dirty/untracked working trees
- [x] Add durable local SQLite queue with idempotency, worker leases, bounded retries, cancellation, and global concurrency cap
- [x] Name each Docker worker and attempt explicit cleanup after an orchestrator timeout; warn if cleanup cannot be confirmed
- [x] Add a dry-run-first utility to reconcile stale, explicitly labelled DebugLens worker containers
- [ ] Add independent container cleanup monitoring and orphan-worker reconciliation
- [x] Add dead-letter tracking, inspection, and explicit operator replay for exhausted infrastructure failures
- [x] Implement bounded provider-backed patch suggestion from user-supplied source context without automatic application
- [ ] Add bounded LLM specialist agents for diagnosis and test planning
- [x] Add local durable orchestration, idempotency, bounded infrastructure retries, timeout handling, and cancellation
- [x] Add durable dead-letter tracking and operator replay tooling
- [ ] Add scheduled retry/backoff policy and operator alerts for dead-letter jobs
- [ ] Enforce tool permissions and human approval in code, not only in prompts
- [ ] Add prompt-injection and tool-boundary red-team tests

## Phase 4: Verification and repair

- [x] Deterministic screenshot baseline comparison with changed-pixel ratio, mean absolute error, and diff bounds
- [x] Add a coarse difference-hash signal and validated dynamic-region masking; this is not a learned perceptual model
- [x] Bounded static DOM accessibility heuristics for labels, names, headings, landmarks, duplicate IDs, and hidden focusables
- [ ] Cross-viewport test matrix, keyboard/screen-reader checks, and full WCAG coverage
- [x] Run approved suites in a network-disabled worker container with no secrets and resource limits
- [ ] Add an independent review of the sandbox boundary and Docker daemon permissions
- [ ] Require green machine-captured checks and explicit human approval before repository changes
- [ ] Add rollback and regression verification

## Data lifecycle

- [x] Add a dry-run-first local SQLite retention CLI that only deletes old terminal workflows and their patch/test/execution child records
- [x] Write an aggregate audit event for explicit retention runs
- [ ] Extend retention/deletion verification to S3 objects, backups, logs, provider-side copies, and container artifacts
- [ ] Add tenant-scoped deletion requests and legal-hold support before multi-user deployment

## Phase 5: Production operations and AWS

- [x] Private encrypted S3 artifact-storage Terraform baseline with KMS, public-access blocking, TLS-only policy, and lifecycle expiry
- [x] Separate least-privilege API/worker ECS task-role policies scoped to S3 prefixes and KMS encryption context (roles are not attached to compute yet)
- [ ] OpenTelemetry traces and redacted structured logs
- [ ] SLOs, dashboards, alerts, quotas, provider budgets, and cost attribution
- [ ] ECS/Fargate, SQS, Step Functions approval callbacks, Secrets Manager, and CloudWatch alarms
- [ ] GitHub OIDC deployment roles, staging environment, rollback, and disaster recovery
- [ ] Authentication, authorisation, rate limits, tenant isolation, and a production security review

The checked items are implemented in this repository. Unchecked items are planned and must not be represented as production-ready capabilities. The benchmark runner exists, but the repository does not yet include a sufficiently representative, independently labelled benchmark dataset.

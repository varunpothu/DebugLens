# Roadmap

## Phase 0: Reliable foundation

- [x] Typed response contract and deterministic mock mode
- [x] FastAPI health/readiness and upload endpoint
- [x] Image decoding, MIME allow-list, upload size and pixel bounds
- [x] SQLite run persistence and audit trail for local workflows
- [x] API endpoints for creating runs, listing runs, reading a run, and recording legal transitions
- [x] Unit, API, workflow, model-evaluation, provider-contract, and target-validation tests
- [x] Threat model, architecture, evaluation criteria, and operations guidance
- [x] CI pipeline for Python 3.11/3.12, Ruff, pytest, and mypy
- [ ] Confirm CI passes on the latest commit before release

## Phase 1: Multimodal analysis and model evaluation

- [x] Provider-neutral vision contract
- [x] Opt-in OpenAI-compatible, Anthropic, and Gemini adapters
- [x] Structured output validation and safe provider failure handling
- [x] Mocked HTTP contract tests for each provider
- [x] Side-by-side model comparison harness for latency and output summaries
- [x] Deterministic evidence summary, hypothesis ranking, test-case proposal, and assurance blockers
- [ ] Add a versioned, labelled screenshot benchmark with human-adjudicated ground truth
- [ ] Add privacy-preserving redaction before external provider calls
- [ ] Add retry budgets, provider rate limits, token/cost telemetry, and prompt-version tracking

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
- [x] Human-authored patch proposals with digest, rationale, risk, and rollback plan
- [x] Test-result records tied to the exact patch digest
- [x] Gate verification on a passing report for the current patch digest
- [ ] Implement isolated test execution and independently captured test logs
- [ ] Implement patch generation from source context without automatic application
- [ ] Add bounded LLM specialist agents for diagnosis and test planning
- [ ] Add durable orchestration, idempotency, retries, timeout handling, cancellation, and dead-letter queue
- [ ] Enforce tool permissions and human approval in code, not only in prompts
- [ ] Add prompt-injection and tool-boundary red-team tests

## Phase 4: Verification and repair

- [ ] Screenshot baseline comparison and perceptual metrics
- [ ] Accessibility checks and cross-viewport test matrix
- [ ] Run tests in an isolated worker with no secrets and restricted egress
- [ ] Require green machine-captured checks and explicit human approval before repository changes
- [ ] Add rollback and regression verification

## Phase 5: Production operations and AWS

- [x] Private encrypted S3 artifact-storage Terraform baseline with KMS, public-access blocking, TLS-only policy, and lifecycle expiry
- [ ] OpenTelemetry traces and redacted structured logs
- [ ] SLOs, dashboards, alerts, quotas, provider budgets, and cost attribution
- [ ] ECS/Fargate, SQS, Step Functions approval callbacks, Secrets Manager, and CloudWatch alarms
- [ ] GitHub OIDC deployment roles, staging environment, rollback, and disaster recovery
- [ ] Authentication, authorisation, rate limits, tenant isolation, and a production security review

The checked items are implemented in this repository. Unchecked items are planned and must not be represented as production-ready capabilities.

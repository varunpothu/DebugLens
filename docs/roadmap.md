# Roadmap

## Phase 0: Reliable foundation

- [x] Typed response contract and deterministic mock mode
- [x] FastAPI health/readiness and upload endpoint
- [x] Image decoding, MIME allow-list, upload size and pixel bounds
- [x] Unit, API, workflow, model-evaluation, and target-validation tests
- [x] Threat model, architecture, evaluation criteria, and operations guidance
- [x] CI pipeline for Python 3.11/3.12, Ruff, pytest, and mypy
- [ ] Confirm CI passes on the latest commit before release

## Phase 1: Multimodal analysis and model evaluation

- [x] Provider-neutral vision contract
- [x] Opt-in OpenAI-compatible, Anthropic, and Gemini adapters
- [x] Structured output validation and safe provider failure handling
- [x] Side-by-side model comparison harness for latency and output summaries
- [ ] Add a versioned, labelled screenshot benchmark with human-adjudicated ground truth
- [ ] Add privacy-preserving redaction before external provider calls
- [ ] Add retry budgets, provider rate limits, token/cost telemetry, and prompt-version tracking
- [ ] Add contract tests with mocked HTTP responses for every provider

## Phase 2: Browser evidence

- [x] Initial Playwright capture library
- [x] Exact hostname allow-list and URL validation tests
- [x] Capture screenshot, page title, tag counts, console error types, and failed-request counts
- [ ] Integrate the collector with the API through an asynchronous job interface
- [ ] Run in a disposable container with network egress controls and DNS/SSRF protection
- [ ] Add resource quotas, cancellation, job timeouts, artifact expiry, and reproduction metadata

## Phase 3: Agentic workflow

- [x] Explicit workflow state machine and audit events
- [x] Documented specialist-agent responsibilities and approval gates
- [ ] Implement bounded perception, evidence correlation, diagnosis, test planning, and verification tasks
- [ ] Add durable orchestration, idempotency, retries, timeout handling, cancellation, and dead-letter queue
- [ ] Enforce tool permissions and human approval in code, not only in prompts
- [ ] Add prompt-injection and tool-boundary red-team tests

## Phase 4: Verification and proposed repair

- [ ] Screenshot baseline comparison and perceptual metrics
- [ ] Accessibility checks and cross-viewport test matrix
- [ ] Generate patch diffs only, with patch digest and rationale
- [ ] Run tests in an isolated worker with no secrets and restricted egress
- [ ] Require green checks and explicit human approval before repository changes
- [ ] Add rollback and regression verification

## Phase 5: Production operations and AWS

- [ ] OpenTelemetry traces and redacted structured logs
- [ ] SLOs, dashboards, alerts, quotas, provider budgets, and cost attribution
- [ ] AWS infrastructure as code, staging environment, rollback, and disaster recovery
- [ ] Secrets Manager, least-privilege IAM, private networking, encrypted artifact storage, and lifecycle policies
- [ ] Security review, release checklist, privacy review, and incident playbooks

The checked items are implemented in this repository. Unchecked items are planned and must not be represented as production-ready capabilities.

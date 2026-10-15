# Roadmap

## Phase 0: Reliable foundation (current scaffold)

- [x] Typed response contract and deterministic mock mode
- [x] FastAPI health/readiness and upload endpoint
- [x] Image decoding, MIME allow-list, size and pixel bounds
- [x] Unit and API tests
- [x] Threat model, architecture and evaluation criteria
- [ ] Run CI and fix any environment-specific failures

## Phase 1: Real multimodal analysis

- [ ] Define provider protocol and adapter contract
- [ ] Add opt-in provider using structured outputs and timeout/retry budget
- [ ] Add redaction and explicit consent/provider configuration
- [ ] Add contract tests, recorded fixtures, and benchmark comparisons
- [ ] Record model, prompt, configuration, latency and cost metadata

## Phase 2: Browser evidence

- [ ] Playwright worker in a disposable container
- [ ] Allow-listed URLs only; block local/private/metadata networks
- [ ] Capture screenshot, DOM selectors, console, network failures, viewport and browser versions
- [ ] Reproduction recipe and artefact expiry

## Phase 3: Agentic workflow

- [ ] Typed tasks for perception, evidence correlation, diagnosis, test planning, and verification
- [ ] Durable state machine, idempotency, retry budget, timeout, cancellation and dead-letter path
- [ ] Human approval for target access, patch application, and release actions
- [ ] Prompt-injection and tool-permission tests

## Phase 4: Verification and proposed repair

- [ ] Baseline image comparison and perceptual metrics
- [ ] Accessibility checks and cross-viewport test matrix
- [ ] Generate patch diffs only
- [ ] Run tests in isolated worker with no secrets and restricted egress
- [ ] Require green checks and human approval before repository changes

## Phase 5: Production operations

- [ ] OpenTelemetry traces and redacted structured logs
- [ ] SLOs, dashboards, alerts, quotas and cost budgets
- [ ] AWS IaC, staging environment, rollback and disaster recovery
- [ ] Security review, release checklist and incident playbooks

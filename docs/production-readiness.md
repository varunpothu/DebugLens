# Production readiness gates

**Status: not production-ready.** This checklist is a release gate, not a claim that the unchecked controls exist.

## Implemented local controls

- API supports a configured bearer token; production startup refuses to run without `API_ACCESS_TOKEN`.
- Uploads have content-type, byte-size, image-format, and pixel-count checks.
- Common sensitive text patterns are redacted before outbound vision-provider calls.
- External vision-provider image transfer is denied by default because screenshot pixels are not redacted; the operator must explicitly set `ALLOW_UNREDACTED_SCREENSHOTS=true` to opt in. This is not a substitute for OCR redaction or privacy review.
- Browser capture is disabled by default and requires an exact hostname allow-list.
- Proposed patches remain review-only; test reports are bound to patch/workspace digests.
- The isolated test worker uses a non-root user, read-only workspace, no network, dropped capabilities, no-new-privileges, and CPU/memory/PID/time/output bounds.
- CI runs Ruff, pytest, mypy on Python 3.11 and 3.12 and exercises the worker container.

These are partial safeguards. They do not provide multi-user identity, RBAC, tenant isolation, a production-grade rate limiter, or a substitute for independent review.

## Required before any public deployment

### Identity and access

- [ ] Integrate a supported identity provider; do not share one static bearer token among end users.
- [ ] Enforce server-derived actor identity and role-based permissions on every read and write.
- [ ] Add tenant-scoped database queries and object-storage paths; test cross-tenant access denial.
- [ ] Apply gateway-level request/body limits and distributed rate limits, including provider cost quotas.
- [ ] Decide whether documentation and readiness endpoints should be private in the deployment environment.

### Data protection

- [ ] Review provider retention, training, region, and contractual settings.
- [ ] Add OCR-assisted redaction or a manual review gate for screenshots before external transfer; the current explicit opt-in is only a fail-closed consent gate.
- [ ] Define retention/deletion for database rows, logs, screenshots, browser artifacts, and backups.
- [ ] Verify logs never contain tokens, raw screenshots, full prompts, or unredacted issue/context text.
- [ ] Test redaction against obfuscated values and maintain a versioned synthetic test corpus.

### Execution and browser isolation

- [ ] Obtain an independent review of Docker daemon permissions, container escape assumptions, bind mounts, and cleanup behaviour.
- [ ] Run browser capture in a disposable worker with enforced egress filtering, DNS rebinding protection, and private/metadata IP blocking.
- [ ] Verify cancellation kills descendants and that timed-out containers/artifacts are cleaned up.
- [ ] Add adversarial patch, prompt-injection, filesystem, network, and resource-exhaustion tests.
- [ ] Require machine-captured green checks plus explicit, attributable human approval for repository changes.

### Reliability and operations

- [ ] Deploy to a dedicated staging environment with least-privilege cloud roles and secret-manager integration.
- [ ] Add structured redacted logs, distributed traces, metrics, SLOs, alerts, and cost attribution.
- [ ] Set provider, compute, storage, and per-tenant budgets with fail-closed behaviour.
- [ ] Exercise backup restore, database migration, incident response, key rotation, and rollback.
- [ ] Run dependency, secret, container, and infrastructure scans and resolve or formally accept findings.
- [ ] Obtain independent security/privacy sign-off before production traffic.

## Local verification

From a clean checkout, run:

~~~powershell
ruff check .
pytest -q
mypy app
~~~

The CI workflow repeats these checks on Python 3.11 and 3.12 and builds/runs the network-disabled test worker. Passing CI proves only the checks it runs; it does not prove production security.

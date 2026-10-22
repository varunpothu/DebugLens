# Production readiness gates

**Status: not production-ready.** This checklist is a release gate, not a claim that the unchecked controls exist.

## Implemented local controls

- API supports a configured shared bearer token; startup outside `local`, `development`, and `test` refuses tokens shorter than 32 non-whitespace characters. Non-local workflow audit events use the configured `API_SERVICE_ACTOR` rather than trusting actor labels supplied in request bodies.
- The development Docker Compose port is bound to `127.0.0.1` so it is not published on every host interface; this is a local-development default, not a production ingress configuration. This is still not per-user identity, RBAC, or tenant isolation.
- Uploads have content-type, byte-size, image-format, and pixel-count checks; an ASGI guard bounds complete `/v1/` write bodies even when chunked requests omit `Content-Length`, while the app guard rejects malformed or oversized declared lengths.
- API responses add `nosniff`, frame-denial, no-referrer, and no-store headers, and correlation IDs are restricted to a short safe character set. The ASGI body guard caps chunked `/v1/` write requests without `Content-Length` by buffering at most the configured limit; it does not replace reverse-proxy limits, and concurrent bounded buffers still require gateway concurrency controls.
- Write/analysis POST endpoints use a bounded, thread-safe process-local fixed-window limiter with `429` and `Retry-After`; it is a local guardrail, not a shared limiter across processes or hosts.
- A dry-run-first CLI can delete old terminal workflows and related local SQLite records, with an aggregate retention audit event. It does not delete S3 objects, backups, logs, provider-side copies, or containers.
- Common sensitive text patterns are redacted before outbound vision-provider calls.
- External vision-provider image transfer is denied by default because screenshot pixels are not redacted; the operator must explicitly set `ALLOW_UNREDACTED_SCREENSHOTS=true` to opt in. This is not a substitute for OCR redaction or privacy review.
- Browser capture is disabled by default, requires an exact hostname allow-list, and is blocked outside local/development/test until an isolated browser worker is deployed.
- Proposed patches remain review-only; test reports are bound to patch/workspace digests.
- The isolated test worker uses a non-root user, read-only workspace, no network, dropped capabilities, no-new-privileges, and CPU/memory/PID/time/output bounds.
- CI runs Ruff, pytest, mypy on Python 3.11 and 3.12 and exercises the worker container.

These are partial safeguards. `API_SERVICE_ACTOR` is a service identity, not a human identity provider; these controls do not provide per-user identity, RBAC, tenant isolation, a distributed production-grade rate limiter, or a substitute for independent review.

## Required before any public deployment

### Identity and access

- [ ] Integrate a supported identity provider; do not share one static bearer token among end users.
- [ ] Enforce server-derived actor identity and role-based permissions on every read and write.
- [ ] Add tenant-scoped database queries and object-storage paths; test cross-tenant access denial.
- [ ] Apply gateway-level request/body limits and distributed rate limits, including provider cost quotas.
- [x] Disable interactive API documentation and OpenAPI schema routes outside local/development/test environments; readiness remains an operational endpoint and should be restricted at the ingress where appropriate.

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

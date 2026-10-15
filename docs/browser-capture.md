# Browser evidence capture

The optional Playwright collector captures a viewport-sized screenshot, page title, viewport metadata, bounded DOM tag counts (up to 10,000 elements), console error types, page error classes, and a failed-request count. It reports when DOM counting was truncated and deliberately avoids storing raw DOM text and full request URLs, which may contain personal data or secrets.

## Guardrails

- Configure exact approved hostnames; no wildcard suffix matching.
- Reject URL credentials, non-HTTP schemes, IP-literal targets, non-default ports, and private/loopback/link-local IP literals.
- Intercept subresource requests and reject hosts outside the allow-list.
- Permit only GET and HEAD requests, block downloads and service workers, and apply navigation timeouts.
- Run in a disposable container with egress firewall rules. Application-level host validation alone cannot fully prevent DNS rebinding or all network-layer SSRF.
- Do not attach production cookies, cloud credentials, local browser profiles, or unrestricted filesystem access.
- Keep screenshots synthetic or redacted; define retention and deletion rules before storing artefacts.

## Scope and limitations

The collector is wired to the optional `/v1/debug-runs/{workflow_id}/browser-evidence` API endpoint and attaches minimised evidence to a run. The endpoint is disabled by default. Before use beyond a local controlled demo, add tenant-aware authorisation, isolated worker deployment, network egress enforcement, DNS rebinding protection, concurrency/resource quotas, cancellation, artifact expiry, and integration tests against a controlled demo site. Never enable it for arbitrary user-supplied URLs.

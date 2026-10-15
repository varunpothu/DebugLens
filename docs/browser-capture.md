# Browser evidence capture

The optional Playwright collector captures a screenshot, page title, viewport metadata, tag counts, console error types, page error classes, and a failed-request count. It deliberately avoids storing raw DOM text and full request URLs, which may contain personal data or secrets.

## Guardrails

- Configure exact approved hostnames; no wildcard suffix matching.
- Reject URL credentials, non-HTTP schemes, IP-literal targets, and private/loopback/link-local IPs.
- Intercept subresource requests and reject hosts outside the allow-list.
- Permit only GET and HEAD requests, block downloads and service workers, and apply navigation timeouts.
- Run in a disposable container with egress firewall rules. Application-level host validation alone cannot fully prevent DNS rebinding or all network-layer SSRF.
- Do not attach production cookies, cloud credentials, local browser profiles, or unrestricted filesystem access.
- Keep screenshots synthetic or redacted; define retention and deletion rules before storing artefacts.

## Scope and limitations

The collector is not yet wired into the public API or the workflow state machine. The next integration must add tenant-aware authorisation, job timeouts, resource quotas, a queue, isolated worker deployment, DNS/egress enforcement, artifact expiry, and integration tests against a controlled demo site. Never enable it for arbitrary user-supplied URLs.

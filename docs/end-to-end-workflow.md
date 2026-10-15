# End-to-end debugging workflow

## Local lifecycle

1. Submit a screenshot and concise issue report.
2. DebugLens validates the image bytes, file format, dimensions, and upload limit.
3. The configured vision provider returns structured findings; mock mode explicitly reports that it did not inspect pixels.
4. DebugLens stores a durable local run record, structured analysis, screenshot digest, and audit events in SQLite.
5. The run enters `human_review`. A reviewer can record reproduction, patch-proposal, testing, verification, rejection, or cancellation transitions only when allowed by the state machine.
6. An approved browser capture can collect additional visual/runtime signals from an exact allow-listed test hostname. The raw screenshot is analysed in memory and is not retained by the run store.
7. A verified state is an audit assertion by the named actor, not proof that DebugLens itself executed the tests. The reviewer must include the evidence in the reason and follow the documented checks.

## API routes

- `POST /v1/debug-runs`: create an analysis run from a screenshot.
- `GET /v1/debug-runs`: list recent run summaries.
- `GET /v1/debug-runs/{workflow_id}`: retrieve the full run and audit history.
- `POST /v1/debug-runs/{workflow_id}/transitions`: record a legal workflow transition.
- `POST /v1/debug-runs/{workflow_id}/browser-evidence`: capture a page and attach minimised evidence, disabled by default.

## Browser capture safety

Set `BROWSER_ENABLED=true` and `BROWSER_ALLOWED_HOSTS=your-test-host.example` only in a disposable environment. The hostname list uses exact matches, not wildcard suffixes. The collector blocks non-allow-listed subresources and non-GET/HEAD requests. Application-level URL validation is not a complete SSRF defence: enforce DNS and network egress restrictions at the worker/container layer. Do not expose the browser endpoint publicly; the API does not yet provide authentication or tenant-level authorisation.

## Persistence and deployment

- Configure `DATABASE_PATH` to a writable path. The default is `./data/debuglens.db`.
- SQLite is suitable for a single local process or a development demo. Use PostgreSQL with migrations, transaction isolation, and tenant-scoped access for multi-user deployment.
- The screenshot bytes are not persisted by the run store. Only the SHA-256 digest and analysis result are retained.
- This initial API is not yet authenticated. Do not expose it to the public internet or use it with confidential issues until authentication, authorisation, rate limits, and tenant isolation are implemented.

## Manual verification checklist

- Confirm expected versus actual behaviour and the exact viewport/browser.
- Reproduce the issue in a controlled environment.
- Capture console errors and failed requests, excluding secrets and personal data.
- Review each finding against the screenshot and any browser evidence.
- Add a regression test that fails before the fix and passes after it.
- Review the exact diff; run the complete test suite and relevant accessibility/visual regression checks.
- Record the actual commands and outcomes before marking the run verified.

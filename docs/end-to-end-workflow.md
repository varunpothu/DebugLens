# End-to-end debugging workflow

## Local lifecycle

1. Submit a screenshot and concise issue report.
2. DebugLens validates the image bytes, file format, dimensions, and upload limit.
3. The configured vision provider returns structured findings; mock mode explicitly reports that it did not inspect pixels.
4. DebugLens stores a durable local run record, structured analysis, screenshot digest, and audit events in SQLite.
5. Deterministic investigation stages summarise evidence, rank unverified hypotheses, propose regression checks, and create assurance blockers. They are bounded orchestration steps, not autonomous LLM agents.
6. The run enters `human_review`. A reviewer records reproduction before a patch proposal is allowed.
7. A human-authored unified diff can be saved as a patch proposal. DebugLens stores its SHA-256 digest, rationale, risk, rollback plan, and author. It never applies or executes the diff.
8. A reviewer runs tests in an isolated environment and records the command, outcome, summary, actor, and exact patch digest. These are self-reported results, not independently verified execution.
9. The run can move to `verified` only from `tested` when the latest recorded test result is passing and references the current patch digest.
10. An approved browser capture can collect additional visual/runtime signals from an exact allow-listed test hostname. The raw screenshot is analysed in memory and is not retained by the run store.

## API routes

- `POST /v1/debug-runs`: create an analysis run from a screenshot.
- `GET /v1/debug-runs`: list recent runs.
- `GET /v1/debug-runs/{workflow_id}`: retrieve analysis, patch proposal, test reports, and audit history.
- `POST /v1/debug-runs/{workflow_id}/transitions`: record a legal state transition. Patch-proposed and tested states require their dedicated endpoints.
- `POST /v1/debug-runs/{workflow_id}/patch-suggestions`: ask the configured provider for a review-only diff from supplied source context.
- `POST /v1/debug-runs/{workflow_id}/patch-proposals`: store a manually prepared diff only after reproduction.
- `POST /v1/debug-runs/{workflow_id}/test-results`: record a test result for the exact current patch digest.
- `POST /v1/debug-runs/{workflow_id}/browser-evidence`: capture a page and attach minimised evidence, disabled by default.

## AI-assisted patch suggestions

The suggestion endpoint uses the configured provider to propose a unified diff for one repository-relative target file. It validates path traversal, checks that the diff headers match the target file, and refuses multi-file diffs. It does not fetch source code from GitHub, apply the patch, execute commands, or claim tests ran. The caller supplies source context; when a real provider is enabled, that context and issue report are transmitted to the provider. Do not submit secrets or confidential source code without approval.

## Patch and test integrity

The patch digest is calculated from the exact UTF-8 diff text. Any change to the diff produces a different digest and requires a new proposal. Test reports must reference the current digest. A passing report is an assertion from the named reviewer, not proof that DebugLens executed the command. Before marking a run verified, independently inspect the diff and actual test output, and add a regression test that fails before the fix.

## Browser capture safety

Set `BROWSER_ENABLED=true` and `BROWSER_ALLOWED_HOSTS=your-test-host.example` only in a disposable environment. The hostname list uses exact matches, not wildcard suffixes. The collector blocks non-allow-listed subresources and non-GET/HEAD requests. Application-level URL validation is not a complete SSRF defence: enforce DNS and network egress restrictions at the worker/container layer. Browser capture is disabled by default and should remain unavailable to public users until a disposable browser worker and network-level egress controls are deployed. The API supports an optional shared bearer token, but this is not per-user authentication, role-based access control, or tenant-level authorisation.

## Persistence and deployment

- Configure `DATABASE_PATH` to a writable path. The default is `./data/debuglens.db`.
- SQLite is suitable for a single local process or a development demo. Use PostgreSQL with migrations, transaction isolation, and tenant-scoped access for multi-user deployment.
- The run store retains screenshot digests and structured analysis, not original uploaded screenshot bytes.
- The API can require a shared bearer token, and non-local startup refuses a missing or weak token. This is a local access gate only: it does not provide per-user identity, role-based permissions, tenant isolation, or a distributed rate limiter. Do not expose the service to the public internet or use it with confidential issues until those controls, provider privacy review, and independent sandbox review are complete.

## Manual verification checklist

- Confirm expected versus actual behaviour and the exact viewport/browser.
- Reproduce the issue in a controlled environment.
- Capture console errors and failed requests, excluding secrets and personal data.
- Review each finding against the screenshot and any browser evidence.
- Review the exact patch digest, diff, rationale, risk, and rollback plan.
- Run the regression test and full relevant suite in an isolated environment.
- Record actual commands and outcomes, then mark the run verified only after independent review.

# Operations guide

## Local development

Use Python 3.11 or 3.12, create a virtual environment, install the dev extra, and run pytest, Ruff and mypy before opening a pull request.

## Failure handling

- Invalid upload: return 415, 413 or 422; do not retry.
- Invalid context: return 400; correct the request.
- Provider unavailable: return 503 without exposing credential or provider internals.
- Provider request budget exhausted: return 429 with `Retry-After`; do not automatically retry. The default provider budget is process-local and does not enforce account-wide or billing limits.
- Timeout: mark the workflow failed or retry only within a configured budget.
- Test failure: preserve the failure result; never convert it into success after a retry without recording the earlier failure.
- Suspected sensitive data: stop external processing, restrict access, follow the organisation's incident and deletion process.

## Production signals

Monitor request count, rejection rate, p50/p95 latency, provider error/timeout/rate-limit rate, queue depth, dead-letter count, analysis completion rate, provider-reported token usage and actual provider spend from billing data, test flakiness, human override rate, and unsafe-action attempts. Token counts are not a dollar-cost estimate; provider pricing and account-level budgets must be managed separately.

## Incident response checklist

1. Disable the affected provider or workflow capability using configuration/feature flags.
2. Preserve redacted logs and correlation IDs; avoid copying raw screenshots into tickets.
3. Determine affected tenants, artefacts, model/provider versions, and time window.
4. Revoke exposed credentials and rotate secrets if needed.
5. Delete affected artefacts according to policy and legal requirements.
6. Document root cause, impact, remediation, and regression tests.
7. Re-enable only after the relevant release gate passes.


## SQLite backup and restore

Create a consistent snapshot of the configured database with SQLite's online backup API. The destination must be a new file; the command verifies SQLite integrity, writes with restrictive file permissions, and prints a SHA-256 digest.

```powershell
python -m app.db_backup backup --destination .\backups\debuglens-2026-10-22.sqlite
```

Restore a snapshot to a new database path, then inspect it before switching the application to use it:

```powershell
python -m app.db_backup restore --source .\backups\debuglens-2026-10-22.sqlite --destination .\data\debuglens-restored.sqlite
```

The restore command refuses to overwrite an existing file. For a production recovery, stop the application, preserve the current database and its WAL/SHM files, restore to a new path, verify the restored data, then deliberately switch the configured database path and restart. Keep backups encrypted and off-host in an approved storage location. The optional AWS host now has a daily systemd timer configured to upload SQLite snapshots and SHA-256 metadata to the private S3 `backups/` prefix using KMS encryption; Terraform configures a separate retention window. This remains inactive until the host is deployed. Verify CloudWatch backup logs, the S3 object and its metadata, and a complete restore drill before relying on the schedule.

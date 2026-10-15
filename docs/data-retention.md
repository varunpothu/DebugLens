# Local data retention

**Scope:** this utility manages records in the local SQLite database only. It does not delete S3 objects, backups, application logs, provider-side copies, screenshots stored elsewhere, or Docker containers.

## Policy

- The CLI defaults to a 90-day retention window.
- Only terminal workflows (`verified`, `rejected`, `failed`, `cancelled`) whose **creation time** is older than the retention cutoff are eligible.
- Active/in-progress workflows are never removed by this utility.
- Related patch proposals, manually reported test results, and signed execution reports are deleted with an eligible workflow.
- An aggregate record is written to the local `retention_events` table when `--apply` is used. It records the cutoff, retention period, count and operator label, not the deleted workflow IDs.
- The utility defaults to a dry run. Deletion requires the explicit `--apply` flag.

This is a local operator utility, not a tenant-aware deletion API. Do not expose it as an unauthenticated web endpoint. Before multi-user use, implement authenticated subject/tenant scoping and a documented legal-hold/retention policy.

## Usage

From the repository root, preview the number of eligible runs:

```powershell
python -m runner.retention --retention-days 90
```

Delete eligible local database records only after reviewing the preview:

```powershell
python -m runner.retention --retention-days 90 --apply --actor local-operator
```

Use a longer or shorter window by changing `--retention-days` (allowed range: 1–3650). The utility will not delete non-terminal workflows, even if they are older than the cutoff.

## Verification

```powershell
pytest -q tests/test_retention.py
```

The tests cover dry-run non-destructiveness, terminal-state selection, related-record cleanup, an aggregate audit event, and invalid retention settings.

## Production gaps

- S3 lifecycle expiry is configured separately in Terraform and must be deployed/verified in the target AWS account.
- Backup retention and restore/deletion behaviour must be configured and tested independently.
- Provider-side retention is governed by provider contracts/settings.
- Logs and container artifacts require separate retention controls.
- A production service needs tenant-scoped access control, legal holds where applicable, deletion requests, and independent verification of all data stores.
# Isolated test worker

## Status

The repository contains a fixed-suite worker (`runner/worker.py`), a minimal image (`runner/Dockerfile`), and a host-side Docker orchestrator (`runner/orchestrate.py`). The orchestrator submits HMAC-signed results to `/v1/debug-runs/{workflow_id}/execution-results`. The worker itself receives no signing secret. This is a local prototype, not production-ready multi-tenant execution. The existing `/test-results` endpoint remains a reviewer-reported result.

## Allowed suites

The worker accepts only `DEBUGLENS_TEST_SUITE=pytest`, `ruff`, or `mypy`. It never accepts a shell string or arbitrary executable. Each command is an argument array with `shell=False`. Timeouts are capped at 300 seconds, workspace snapshots are limited to 10,000 regular files and 50 MiB, symlinks are rejected, and output is capped at 20,000 characters in the returned JSON.

The result includes the SHA-256 digest of the exact workspace snapshot, suite name, command, exit code, timeout state, duration, completion timestamp, and output-truncation flag. A timeout or non-zero exit is not a pass. The snapshot digest is separate from the proposed patch digest; an orchestrator must bind both digests to the same reviewed run before treating the result as relevant evidence.

## Build and run manually

Build from the repository root:

```bash
docker build -f runner/Dockerfile -t debuglens-test-worker:local .
```

Prepare a dedicated workspace containing only the reviewed source snapshot, then run a suite with the workspace mounted read-only. Example on Linux/macOS:

```bash
docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --memory 512m \
  --cpus 1 \
  --pids-limit 128 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --mount type=bind,src="$PWD/reviewed-workspace",dst=/workspace,readonly \
  -e DEBUGLENS_TEST_SUITE=pytest \
  debuglens-test-worker:local
```

Run `ruff` or `mypy` by changing only `DEBUGLENS_TEST_SUITE`. Do not mount the Docker socket, credentials, the host home directory, or writable host paths. Do not run untrusted source outside this container profile. The image contains test tools and dependencies installed at build time; the mounted workspace supplies the code under test. Network access is intentionally disabled, so tests requiring external services should use local fixtures.

## Submit a result to the API

Configure the API with a separate signing secret (at least 32 characters) using `EXECUTION_SIGNING_SECRET`. On the trusted host, set the same value as `DEBUGLENS_EXECUTION_SIGNING_SECRET`; optionally set `DEBUGLENS_API_ACCESS_TOKEN` if API bearer-token protection is enabled. Never pass the signing secret as a Docker `-e` argument or mount it into the worker.

Build the image, prepare a reviewed workspace snapshot, then run the orchestrator from the repository root:

```bash
docker build -f runner/Dockerfile -t debuglens-test-worker:local .
python -m runner.orchestrate \
  --workspace ./provisioned-workspace \
  --patch-file ./reviewed.patch \
  --manifest ./provisioned-workspace-manifest.json \
  --suite pytest \
  --workflow-id YOUR_WORKFLOW_ID \
  --actor local-reviewer \
  --api-url http://127.0.0.1:8000
```

The orchestrator checks the worker exit status, adds the current patch digest, signs the canonical payload, and submits it to the API. It returns a non-zero exit code when the suite fails or submission is rejected. The orchestrator now requires the manifest and original patch file used by provisioning. It re-hashes the patch bytes and mounted workspace before execution, then rejects a worker result if its suite or workspace digest differs from the host snapshot. The manifest binds the base-tree digest, patch digest, target path, and final workspace digest. The base_revision field is operator-supplied audit metadata; it is not independently resolved against Git, so the base-tree digest is the cryptographic identifier of the actual source snapshot.


## Provision a reviewed workspace

Start from a trusted source snapshot and a single-file unified diff that has already been reviewed. The provisioner copies the source into a new directory, excludes common caches, local databases and secret-like files, rejects symlinks and oversized trees, then applies the patch only when every removed/context line exactly matches the base file. It never writes to the base tree and never executes the patched code.

```bash
python -m runner.provision \
  --base-workspace ./trusted-base \
  --patch-file ./reviewed.patch \
  --target-file app/styles.css \
  --output-workspace ./provisioned-workspace \
  --base-revision YOUR_REVIEWED_BASE_REF \
  --manifest ./provisioned-workspace-manifest.json
```

Then run the test suite using that exact workspace, patch and manifest:

```bash
python -m runner.orchestrate \
  --workspace ./provisioned-workspace \
  --patch-file ./reviewed.patch \
  --manifest ./provisioned-workspace-manifest.json \
  --suite pytest \
  --workflow-id YOUR_WORKFLOW_ID \
  --actor local-reviewer \
  --api-url http://127.0.0.1:8000
```

The manifest must be stored outside the provisioned workspace. The output directory must not already exist. The provisioner supports existing UTF-8 text files only; file creation/deletion, multiple-file diffs, binary changes, rename/copy operations and fuzzy patching are deliberately unsupported. The base revision must now be the full 40-character SHA of the checked-out Git HEAD. Provisioning rejects a different HEAD, a dirty working tree, untracked files, and a source directory that is not the repository root. The manifest stores that verified commit SHA alongside the base-tree digest. Review the manifest before trusting a result.


## Durable local execution queue

The optional SQLite queue adds idempotent submissions, bounded retries for worker/infrastructure failures, expiring worker leases, cancellation requests, output caps, and a global concurrency limit across queue workers sharing the same database. It is a local trusted-host utility, not a public API. The signing secret and API token remain in the worker process environment and are never stored in job payloads.

Enqueue a job using the same provisioned workspace, patch, and manifest:

```bash
python -m runner.job_queue enqueue \
  --workspace ./provisioned-workspace \
  --patch-file ./reviewed.patch \
  --manifest ./provisioned-workspace-manifest.json \
  --suite pytest \
  --workflow-id YOUR_WORKFLOW_ID \
  --actor local-reviewer \
  --api-url http://127.0.0.1:8000 \
  --idempotency-key workflow-123-pytest-v1
```

Start a worker with a maximum of two concurrent jobs:

```bash
python -m runner.job_queue worker --concurrency 2
```

Inspect and cancel jobs:

```bash
python -m runner.job_queue list --limit 20
python -m runner.job_queue cancel YOUR_JOB_ID
python -m runner.job_queue dead-letter --limit 20
python -m runner.job_queue replay YOUR_JOB_ID
```

Set `DEBUGLENS_QUEUE_DATABASE` to choose a local queue database path. Reusing an idempotency key with the same payload returns the existing job; reusing it with a different payload is rejected. Running cancellation sends an interrupt to the orchestrator process group and escalates if necessary. The orchestrator gives each Docker worker a unique name and attempts `docker rm -f` after a timeout; if cleanup cannot be confirmed, the result output warns the operator to inspect the Docker host. This is per-run best effort, not independent orphan-container monitoring. A worker lease expires after seven minutes; another worker can recover a stale job, with at most two attempts. Exhausted infrastructure failures are marked as dead letters and can only be replayed through the explicit operator command. Use the queue only on a trusted host with Docker access. Review cancellation and container cleanup behavior in your own Docker runtime before production use.

## Reconcile stale worker containers

The orchestrator attempts cleanup when its own execution times out. For a host-side reconciliation pass, the optional cleanup utility considers only containers with the `com.debuglens.managed=true` label that are older than the configured threshold (minimum 10 minutes, default 30 minutes). It defaults to dry-run:

```bash
python -m runner.container_cleanup --max-age-seconds 1800
```

Review the output first, then explicitly apply removals:

```bash
python -m runner.container_cleanup --max-age-seconds 1800 --apply
```

The orchestrator adds the management label to newly created workers. The cleanup tool rechecks the label before removal and reports failures. Run it only on the trusted Docker host. It is not a continuously running monitor; an operator or trusted scheduler must invoke it. Do not lower the age threshold below 10 minutes, and do not use it to manage containers that lack the DebugLens label.

## Important limitations

- The worker container is a sandbox boundary only when launched with the restrictions above. Running `runner/worker.py` directly on a host is not isolated.
- The workspace must be created and reviewed by a trusted orchestrator. The provisioner verifies the base Git commit and clean tree, applies the supported diff without executing code, and records the patch/workspace digests; the worker itself does not apply patches.
- The worker's output is evidence, not approval. Human review and explicit approval remain required.
- The manifest is a local integrity check, not a signed attestation of the base revision. Protect the trusted host, patch file, manifest, and Docker daemon; an operator who controls all inputs can forge them.
- Remaining integration work includes authenticated job submission hardening, independent container lifecycle monitoring, and production security review. The API persists the suite and workspace digest and rejects verification when the latest trusted execution report does not match the current patch digest.
- Output is redirected to a temporary file inside the container and only the first 20,001 bytes are read into memory. The container's tmpfs size and memory limit remain important safety boundaries.

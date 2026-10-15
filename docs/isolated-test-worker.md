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
  --workspace ./reviewed-workspace \
  --suite pytest \
  --workflow-id YOUR_WORKFLOW_ID \
  --patch-sha256 YOUR_CURRENT_PATCH_SHA256 \
  --actor local-reviewer \
  --api-url http://127.0.0.1:8000
```

The orchestrator checks the worker exit status, adds the current patch digest, signs the canonical payload, and submits it to the API. It returns a non-zero exit code when the suite fails or submission is rejected. The operator is responsible for ensuring the mounted workspace is the exact reviewed source state corresponding to the patch digest; the prototype does not apply or independently reconstruct a patch.

## Important limitations

- The worker container is a sandbox boundary only when launched with the restrictions above. Running `runner/worker.py` directly on a host is not isolated.
- The workspace must be created and reviewed by a trusted orchestrator; the worker does not apply a patch or verify that a supplied patch digest matches a diff.
- The worker's output is evidence, not approval. Human review and explicit approval remain required.
- Remaining integration work includes trusted workspace provisioning from the reviewed patch, authenticated job submission, queueing/cancellation, container lifecycle management, and production security review. The API persists the suite and workspace digest and rejects verification when the latest trusted execution report does not match the current patch digest.
- Output is redirected to a temporary file inside the container and only the first 20,001 bytes are read into memory. The container's tmpfs size and memory limit remain important safety boundaries.

# Isolated test worker

## Status

The repository now contains a standalone, fixed-suite worker (`runner/worker.py`) and a minimal image definition (`runner/Dockerfile`). It is **not wired to the API** and must not be described as production-ready. The existing `/test-results` endpoint remains a reviewer-reported result, not independently verified execution.

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

## Important limitations

- The worker container is a sandbox boundary only when launched with the restrictions above. Running `runner/worker.py` directly on a host is not isolated.
- The workspace must be created and reviewed by a trusted orchestrator; the worker does not apply a patch or verify that a supplied patch digest matches a diff.
- The worker's output is evidence, not approval. Human review and explicit approval remain required.
- API integration still needs authenticated job submission, one-time workspace provisioning, queueing/cancellation, result signature or trusted transport, persistence of suite and workspace digest, and a gate that rejects stale evidence whenever the patch or workspace changes.
- The current subprocess captures output in memory before truncation. The container memory limit is therefore part of the safety boundary; a future hardening pass should stream output to a bounded file or pipe.

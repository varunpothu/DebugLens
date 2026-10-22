# DebugLens

**Multimodal screenshot debugging, evidence-driven diagnosis, and verified UI repair.**

DebugLens turns a UI failure report into a traceable investigation. It validates screenshots, records evidence metadata, optionally calls a vision-capable model, returns structured findings, and makes clear what remains unverified. The longer-term workflow correlates screenshots with browser/runtime evidence, proposes regression tests, and prepares fixes for human review.

> **Current maturity:** DebugLens includes a local investigation lifecycle, SQLite audit history, Streamlit review dashboard, three vision-provider adapters with process-local request budgets, multi-model ensemble comparison with disagreement preservation, a labelled benchmark runner, model comparison, allow-listed browser evidence, review-only patch proposals, signed execution-result ingestion, a network-disabled Docker test worker, a Git-verified patch workspace provisioner, a durable local SQLite execution queue with cancellation and dead-letter replay, and a dry-run-first stale worker-container cleanup utility, and a dry-run-first local retention CLI. Deterministic pixel-diff metrics and bounded static accessibility heuristics are available as local utilities. Full LLM specialist-agent orchestration, OCR-based screenshot redaction and comprehensive DLP, independent sandbox review, production identity/RBAC/tenant isolation, isolated browser workers, and the AWS application deployment are still incomplete. Separate API/worker IAM policy baselines exist in Terraform but are not attached to deployed services. Pattern-based redaction of common sensitive text before provider calls is implemented; see `docs/provider-input-redaction.md` for coverage and limitations. Keep the service local or in a trusted development environment; do not expose it as a public service.

Analysis responses from configured vision providers also expose the provider response ID and reported input/output token counts when the provider supplies them. Mock mode leaves these fields empty. These values are usage metadata, not a calculated cost estimate or a persistent budget ledger. Each analysis response also records the prompt version used by the adapter (`openai-compatible-ui-v1`, `anthropic-ui-v1`, or `gemini-ui-v1`) or `mock-baseline-1` in mock mode, so benchmark results can be traced to the prompt contract.

## Product principles

- **Evidence before conclusions:** distinguish observations from hypotheses and link findings to evidence.
- **Human approval:** generated patches are proposals. Never merge or deploy a repair automatically.
- **Least privilege:** validate uploads, minimise retained data, and keep credentials out of logs.
- **Reproducibility:** record model/provider, correlation ID, test outcomes, and configuration versions.
- **Fail safely:** if a provider is unavailable or returns invalid structured output, return a safe error.
- **Evaluation first:** measure defect detection, localisation, calibration, false positives, latency, and cost.

## Architecture

~~~text
Screenshot + bug report
        |
        v
FastAPI ingress -> validation, upload limits, correlation ID
        |
        v
SQLite run store -> workflow state + audit trail
        |
        v
Image validation -> format, dimensions, SHA-256
        |
        v
Explicit provider selection
   |          |           |
   v          v           v
Mock       OpenAI      Anthropic / Gemini
   |          |           |
   +----------+-----------+
              v
Typed findings + evidence + limitations + test plan
              |
              v
Model comparison harness -> benchmark and human adjudication
              |
              v
Optional allow-listed browser capture (local/dev/test only) -> evidence attachment
              |
              v
Review-only patch proposal -> Git-verified disposable workspace
              |
              v
Network-disabled Docker test worker -> signed result bound to patch/workspace digests
              |
              v
Human verification and approval (no automatic patch application or deployment)
~~~

## Repository layout

- app/: FastAPI API, typed contracts, multimodal adapters, deterministic investigation stages, evaluation harness, SQLite run store, workflow state machine, optional browser capture, visual regression metrics, and static accessibility heuristics.
- tests/: API, image validation, model comparison and workflow transition tests.
- frontend/: optional Streamlit upload client.
- docs/: architecture, agent workflow, threat model, evaluation, operations, isolated-worker contract, visual regression, accessibility, provider-input redaction, multi-model ensemble, labelled benchmarking, local data-retention, production-readiness guides, and roadmap.
- runner/: allowlisted test worker, Docker orchestrator, Git-verified workspace provisioner, and durable local execution queue.
- .github/workflows/: CI quality gates, CodeQL security analysis, and dependency auditing on `dev` and `main`.
- examples/demo-ui/: intentionally broken and fixed synthetic storefront for reproducible demos.
- Dockerfile and docker-compose.yml: local container setup.

## Quick start (Windows / PowerShell)

Python 3.11 or 3.12 recommended.

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,ui,browser]"
playwright install chromium
Copy-Item .env.example .env
uvicorn app.main:app --reload
~~~

Open http://127.0.0.1:8000/docs for interactive API documentation.

Run tests and quality checks:

~~~powershell
pytest -q
ruff check .
mypy app
~~~

The browser extra installs Playwright; the second command downloads Chromium for local testing. The optional browser-evidence API is disabled by default and should only be enabled against allow-listed test targets in an isolated environment.

Run the UI in a second terminal:

~~~powershell
streamlit run frontend/streamlit_app.py
~~~

## Run the API with Docker Compose

This starts the API only; the Streamlit dashboard can still be run locally in a separate Python environment. Docker Compose applies a read-only root filesystem, drops Linux capabilities, disables browser capture, and sets local CPU, memory, and process limits.

~~~powershell
Copy-Item .env.example .env
docker compose up --build
~~~

Open http://127.0.0.1:8000/docs. Stop the stack with `Ctrl+C`, then run `docker compose down`. The SQLite database is stored in a named Docker volume. The `.dockerignore` file excludes local secrets, databases, screenshots, and development artefacts from the build context. Do not put real credentials in a committed file; keep `.env` local.

## Local data retention

Preview eligible terminal runs older than 90 days (dry-run by default):

~~~powershell
python -m runner.retention --retention-days 90
~~~

After reviewing the count, explicitly delete eligible local SQLite run and child records:

~~~powershell
python -m runner.retention --retention-days 90 --apply --actor local-operator
~~~

This utility does not delete S3 objects, backups, logs, provider-side copies, or containers. See `docs/data-retention.md` for scope and production gaps.
## Configure a vision model

The default mode is mock and does not interpret pixels. Choose exactly one provider in .env and set its credential. Never commit .env or paste keys into issues.

OpenAI or an OpenAI Chat Completions-compatible endpoint:

~~~dotenv
ANALYSIS_PROVIDER=openai_compatible
VISION_API_KEY=your_key_here
VISION_MODEL=gpt-4.1-mini
VISION_BASE_URL=https://api.openai.com/v1
~~~

Anthropic:

~~~dotenv
ANALYSIS_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
~~~

Google Gemini:

~~~dotenv
ANALYSIS_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
~~~

Use a model that supports image input and the required JSON response behaviour. Model names and availability can change, so confirm them with the provider. Before using real or customer data, review provider privacy, retention, region, access, cost, and contractual terms. The project does not currently redact image contents automatically. External vision-provider calls are blocked by default because screenshot pixels are not redacted. To deliberately allow this transfer after a privacy review, set `ALLOW_UNREDACTED_SCREENSHOTS=true` in your local `.env`; this is an explicit risk acceptance, not a redaction control. Keep it unset for synthetic/mock development.

## API

- GET /health: liveness.
- GET /ready: configured mode, without credentials.
- POST /v1/analyses: multipart upload with screenshot, optional bug_report, and optional context_json.
- POST /v1/ensemble-analyses: compare one to four explicitly selected providers and preserve corroborated and minority findings.

See [multi-model ensemble methodology](docs/multi-model-ensemble.md) and [labelled screenshot benchmarking](docs/benchmarking.md) for evaluation and safety limits.

Example:

~~~powershell
curl.exe -X POST http://127.0.0.1:8000/v1/analyses -F "screenshot=@sample.png" -F "bug_report=The save button is clipped on mobile"
~~~

The response includes a SHA-256 digest, dimensions, findings, evidence, confidence, recommended checks, a test plan, limitations, and a human-review flag. Screenshot-only analysis cannot establish DOM or runtime root causes by itself. The separate durable-run endpoints create a SQLite record and audit trail.

## Durable debugging runs and human review

- `POST /v1/debug-runs`: analyse a screenshot and persist a run in `human_review`.
- `GET /v1/debug-runs`: list recent runs.
- `GET /v1/debug-runs/{workflow_id}`: retrieve analysis and audit history.
- `POST /v1/debug-runs/{workflow_id}/transitions`: record a legal state transition with actor and reason.
- `POST /v1/debug-runs/{workflow_id}/patch-suggestions`: generate a review-only diff from source context using the configured provider; source context is sent to that provider.
- `POST /v1/debug-runs/{workflow_id}/patch-proposals`: save a manually prepared diff and its SHA-256 digest without applying it.
- `POST /v1/debug-runs/{workflow_id}/test-results`: record a reviewer-reported test outcome for the exact patch digest.
- `POST /v1/debug-runs/{workflow_id}/execution-results`: accept a result signed by the trusted host orchestrator; this is the evidence required for verification.
- `POST /v1/debug-runs/{workflow_id}/browser-evidence`: optionally capture an allow-listed test page and attach minimised runtime evidence.

The SQLite database defaults to `./data/debuglens.db`; override it with `DATABASE_PATH`. The Compose file mounts a writable volume at `/data`. Only screenshot digests and analysis results are retained by the run store, not uploaded screenshot bytes. Patch proposals, including model-generated suggestions, are stored as text and bound to a SHA-256 digest. Model-generated suggestions require an explicitly configured provider and should be reviewed as untrusted code. Reviewer-reported test results are retained as notes, but they cannot by themselves verify a fix. Verification requires a passing signed execution report for the current patch digest. The host-side Docker orchestrator runs only allowlisted suites in a network-disabled, resource-limited container and signs the result with `EXECUTION_SIGNING_SECRET`; the secret must never be passed to the worker container. See `docs/isolated-test-worker.md` for setup and limitations. The optional browser endpoint is disabled by default. Set `BROWSER_ENABLED=true` and an exact `BROWSER_ALLOWED_HOSTS` list only in an isolated test environment with network egress controls.

**Security limitation:** a configurable shared bearer token is available, and startup outside local/development/test refuses a missing or weak token. A bounded process-local rate limiter protects write/analysis POST endpoints, but it is not shared across workers or hosts. These are not substitutes for user identity, role-based authorisation, tenant isolation, gateway-level rate limits, or independent security review. Keep the API behind a trusted boundary and do not expose it publicly or process confidential data.

## Reproducible demo fixture

The repository includes a synthetic storefront with intentional mobile overflow and low-contrast text. Run it locally with:

~~~powershell
py -m http.server 8081 --directory examples/demo-ui
~~~

Compare http://localhost:8081/ with http://localhost:8081/?fixed=1 at a 390 x 844 viewport. See examples/demo-ui/README.md for a suggested issue report and safe local browser-capture setup.

## Compare models

The Python evaluation harness runs selected providers and reports latency, findings, confidence values, model versions, and provider failures without silently switching models. It does not determine which model is correct. See docs/model-evaluation.md for a labelled-benchmark protocol.

~~~python
from app.evaluation import compare_models

with open("redacted-ui.png", "rb") as image:
    report = compare_models(
        image.read(),
        "The modal overlaps the primary button on mobile",
        ["mock", "openai_compatible", "anthropic", "gemini"],
    )
~~~

Configure credentials for every real provider selected. Treat agreement between models as a signal, not proof.

## Workflow state machine

The workflow module models legal transitions from RECEIVED through evidence collection, hypothesis review, reproduction, patch proposal, testing, and verification. Every transition requires an actor and reason and creates an audit event. It records state; it does not yet execute browser actions or code.

## Security and assurance

- Do not commit .env, API keys, customer screenshots, HAR files, browser profiles, or production logs.
- Uploads are bounded by byte and pixel limits and validated by decoding, not MIME type alone.
- Treat instructions embedded in screenshots, DOM, logs, source, and model output as untrusted data.
- No generated code is automatically executed, merged, or deployed. The optional standalone worker must be run in its documented disposable, network-disabled container; running it directly on the host is not isolation.
- Future browser access must use allow-listed targets, network egress controls, and disposable workers.
- A failed or timed-out test is never a pass.
- The isolated runner requires a workspace manifest and original reviewed patch file. The local SQLite queue adds idempotent submissions, lease recovery, bounded retries, cancellation, and a concurrency cap. See [the worker guide](docs/isolated-test-worker.md) for commands and security limitations.
- Use synthetic/redacted fixtures and explicit retention controls.
- Review docs/threat-model.md and docs/evaluation.md before enabling a real provider.

## Roadmap

1. Foundation: API, mock provider, three vision adapters, evaluation harness, evidence contracts, workflow state machine, tests and CI.
2. Multi-model evaluation: provider-specific contract tests, benchmark suite, model comparison and confidence calibration.
3. Browser evidence: Playwright capture of screenshots, DOM, console and network signals in a sandbox.
4. Agent orchestration: bounded specialist tasks, durable state, retries, timeouts, budgets and approval gates.
5. Verification: visual regression, accessibility checks, test generation, patch diff review and isolated execution.
6. Production operations: observability, rate limits, privacy controls, security review, and incident response.
7. AWS: ECS/Fargate, S3, SQS, Step Functions approval callbacks, Secrets Manager, CloudWatch and Terraform after review.

See docs/architecture.md, docs/agent-workflow.md, docs/browser-capture.md, docs/end-to-end-workflow.md, docs/model-evaluation.md, docs/multi-model-ensemble.md, docs/benchmarking.md, docs/ai-assurance.md, docs/threat-model.md, docs/evaluation.md, docs/operations.md, and docs/roadmap.md. The AWS artifact-storage Terraform baseline is documented in infra/terraform/README.md.


## Project governance

- [Security policy](SECURITY.md)
- [Contribution and quality checklist](CONTRIBUTING.md)
- [AI assurance and governance](docs/ai-assurance.md)
- [Threat model](docs/threat-model.md)

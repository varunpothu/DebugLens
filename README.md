# DebugLens

**Multimodal screenshot debugging, evidence-driven diagnosis, and verified UI repair.**

DebugLens turns a UI failure report into a traceable investigation. It validates screenshots, records evidence metadata, optionally calls a vision-capable model, returns structured findings, and makes clear what remains unverified. The longer-term workflow correlates screenshots with browser/runtime evidence, proposes regression tests, and prepares fixes for human review.

> **Current maturity:** working foundation with a deterministic mock provider, opt-in OpenAI-compatible, Anthropic, and Gemini vision adapters, a side-by-side model evaluation harness, typed evidence contracts, API tests, an auditable workflow state machine, and CI. Browser execution, automated patching, cloud deployment, and production-grade multi-agent orchestration remain roadmap items. This is not yet a production-ready autonomous debugger.

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
Planned: browser evidence -> agent workflow -> human approval
              |
              v
Planned: sandboxed tests -> proposed patch -> human verification
~~~

## Repository layout

- app/: FastAPI API, typed contracts, multimodal adapters, evaluation harness, workflow state machine.
- tests/: API, image validation, model comparison and workflow transition tests.
- frontend/: optional Streamlit upload client.
- docs/: architecture, agent workflow, threat model, evaluation, operations, roadmap.
- .github/workflows/: CI quality gates.
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

The browser extra installs Playwright; the second command downloads Chromium for local testing. Browser capture is a library component and is not exposed as an API endpoint yet.

Run the UI in a second terminal:

~~~powershell
streamlit run frontend/streamlit_app.py
~~~

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

Use a model that supports image input and the required JSON response behaviour. Model names and availability can change, so confirm them with the provider. Before using real or customer data, review provider privacy, retention, region, access, cost, and contractual terms. The project does not currently redact image contents automatically.

## API

- GET /health: liveness.
- GET /ready: configured mode, without credentials.
- POST /v1/analyses: multipart upload with screenshot, optional bug_report, and optional context_json.

Example:

~~~powershell
curl.exe -X POST http://127.0.0.1:8000/v1/analyses -F "screenshot=@sample.png" -F "bug_report=The save button is clipped on mobile"
~~~

The response includes a SHA-256 digest, dimensions, findings, evidence, confidence, recommended checks, a test plan, limitations, and a human-review flag. Screenshot-only analysis cannot establish DOM or runtime root causes by itself.

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
- No generated code is automatically executed, merged, or deployed.
- Future browser access must use allow-listed targets, network egress controls, and disposable workers.
- A failed or timed-out test is never a pass.
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

See docs/architecture.md, docs/agent-workflow.md, docs/model-evaluation.md, docs/threat-model.md, docs/evaluation.md, docs/operations.md, and docs/roadmap.md.

# DebugLens

**Multimodal screenshot debugging, evidence-driven diagnosis, and verified UI repair.**

DebugLens turns a UI failure report into a traceable investigation. It combines screenshot evidence with browser/runtime signals, proposes root-cause hypotheses, creates reproducible test plans, and prepares changes for human review. It is designed as a safe engineering assistant, not an unrestricted autonomous code executor.

> **Current maturity:** foundational scaffold. The initial release provides a working API, deterministic analysis mode, evidence model, and tests. External vision-model integrations, browser execution, cloud deployment, and automated repair are intentionally gated behind explicit configuration and later milestones.

## Product principles

- **Evidence before conclusions:** every finding should point to observed evidence or be labelled as a hypothesis.
- **Human approval:** generated patches are proposals. Never deploy or merge a repair automatically.
- **Least privilege:** uploaded files are validated; secrets and raw customer data should not enter logs.
- **Reproducibility:** store model/provider versions, prompt/config versions, test results, and correlation IDs.
- **Fail safely:** if a model is unavailable, return a clear degraded-mode result rather than inventing a diagnosis.
- **Evaluation first:** measure defect detection, localisation, calibration, false positives, latency, and cost.

## Initial architecture

~~~text
Screenshot / bug report
        |
        v
FastAPI ingress ---- request validation / size limits / correlation ID
        |
        v
Evidence normaliser ---- metadata + redaction hooks + SHA-256
        |
        v
Analysis orchestrator
   |        |          |
   v        v          v
Vision   Runtime    Test-plan
adapter  evidence   generator
   |        |          |
   +--------+----------+
            |
            v
Structured findings + confidence + evidence + limitations
            |
            v
Human review -> sandboxed reproduction -> tests -> proposed patch
            |
            v
Audit record / metrics / CI gate
~~~

## Repository layout

- app/: FastAPI application, configuration, schemas, service layer, and safe provider abstraction.
- tests/: unit and API tests, including validation and degraded-mode behaviour.
- frontend/: lightweight Streamlit client.
- docs/: architecture, threat model, evaluation plan, operations, and roadmap.
- infra/terraform/: AWS deployment design scaffold. Review before applying.
- .github/workflows/: CI quality gates.

## Quick start (Windows / PowerShell)

Python 3.11 or 3.12 recommended.

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
~~~

Open the API docs at http://127.0.0.1:8000/docs.

Run tests:

~~~powershell
pytest -q
ruff check .
mypy app
~~~

Run the optional UI in another terminal:

~~~powershell
streamlit run frontend/streamlit_app.py
~~~

## API

- GET /health: liveness check.
- GET /ready: readiness and configured analysis mode.
- POST /v1/analyses: multipart upload with screenshot, optional bug_report, and optional context_json.

Example:

~~~powershell
curl.exe -X POST http://127.0.0.1:8000/v1/analyses -F "screenshot=@sample.png" -F "bug_report=The save button is clipped on mobile"
~~~

The default provider is deterministic mock mode, suitable for local development and tests. It does not claim to understand the screenshot. Configure a real provider only after reviewing privacy, data retention, region, cost, and contractual requirements.

## Security notes

- Do not commit .env, API keys, customer screenshots, HAR files, browser profiles, or production logs.
- The service rejects unsupported image types and oversized uploads.
- Uploaded screenshots may contain credentials, personal data, internal URLs, or customer information. Use synthetic/redacted fixtures.
- Model output is untrusted input. Treat instructions embedded in screenshots, DOM, logs, and source as data, not authority.
- Any future browser or patch execution must run in an isolated, disposable environment with network and filesystem restrictions.
- No model-generated code is merged, deployed, or executed on the host automatically.

## Roadmap

1. **Foundation:** API, schemas, deterministic provider, tests, lint/type checks.
2. **Vision:** provider interface and opt-in model adapter with structured output validation.
3. **Browser evidence:** Playwright capture, DOM/console/network signals, deterministic reproduction.
4. **Agent workflow:** bounded specialist steps, typed hand-offs, retries, timeouts, budgets, and audit events.
5. **Verification:** visual regression, accessibility checks, test generation, confidence calibration, benchmark dataset.
6. **Assurance:** threat modelling, red-team cases, privacy controls, model evaluation, incident playbooks.
7. **AWS:** container deployment, IAM least privilege, secrets management, encrypted object storage, queues, tracing, alarms, Terraform review and staged rollout.

See docs/architecture.md, docs/threat-model.md, docs/evaluation.md, and docs/roadmap.md.

## Status

This repository is a foundation, not yet a production-ready autonomous debugger. The roadmap explicitly distinguishes implemented functionality from future integrations.
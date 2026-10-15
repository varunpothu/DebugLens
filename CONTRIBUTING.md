# Contributing to DebugLens

Thank you for helping improve DebugLens.

## Development setup

Python 3.11 or 3.12 is recommended.

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,ui,browser]"
~~~

Copy `.env.example` to `.env` for local configuration. Never commit credentials, screenshots, browser traces, or the local SQLite database.

## Before submitting a change

~~~powershell
ruff check .
pytest -q
mypy app
~~~

Changes should include tests for new behaviour, failure cases, and security boundaries. Keep provider calls mocked in CI; do not require live credentials or send test fixtures to external services.

## Engineering expectations

- Treat screenshots, issue reports, DOM text, logs, source files, and model outputs as untrusted data.
- Keep evidence separate from hypotheses and make uncertainty explicit.
- Do not claim that a test ran unless the execution result is actually available.
- Do not automatically apply patches, merge pull requests, or deploy from model output.
- Bind test reports and approval records to the exact patch digest.
- Prefer synthetic fixtures and data minimisation.
- Document new configuration variables and update the threat model when trust boundaries change.
- Keep browser targets allow-listed and disabled by default outside controlled local testing.

## Pull request checklist

- [ ] Tests added or updated.
- [ ] Ruff, pytest, and mypy pass.
- [ ] Public API contracts and docs updated.
- [ ] No secrets or sensitive test data included.
- [ ] Threat model and failure behaviour reviewed.
- [ ] Human approval and rollback behaviour preserved.

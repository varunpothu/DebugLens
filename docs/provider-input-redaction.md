# Provider input redaction

DebugLens applies a deterministic text-pattern redaction pass to the issue/context text sent to a configured external vision provider.

## What is covered

The helper in `app/redaction.py` masks common patterns for:
- Email addresses and common UK National Insurance number shapes.
- Values attached to labels such as `password`, `secret`, `api_key`, `access_token`, and `authorization`.
- Bearer tokens, common GitHub/GitLab tokens, AWS access-key IDs, JWT-shaped strings, private-key blocks, and payment-card-shaped digit sequences.

The pass runs in `app/services/analyzer.py` immediately before the provider adapter is called. The locally returned analysis retains the user's original issue text; this feature is intended to reduce outbound disclosure, not to rewrite local records.

## Important limitations

- Pattern matching is not a data-loss-prevention guarantee. It can miss novel token formats, obfuscated values, identifiers in other countries, and secrets embedded in arbitrary encodings.
- The screenshot bytes are sent to the selected vision provider unchanged. Text visible inside screenshots is **not** OCR-scanned or redacted by this feature.
- Source code, browser DOM, logs, HAR files, and arbitrary nested data are not comprehensively scrubbed by this helper.
- A value may be masked even when it is not sensitive, especially long digit sequences.
- Provider retention, training, residency, and contractual settings must be reviewed separately before real user data is sent.

## Operating guidance

1. Prefer synthetic or intentionally redacted screenshots and issue reports.
2. Do not submit credentials, production user data, or regulated data until a privacy review approves the data flow.
3. Keep provider calls disabled in local tests; CI tests use a mocked provider.
4. Treat redaction as one control among upload validation, access control, retention, logging minimisation, and provider-side privacy settings.
5. Before production, add OCR-assisted image redaction with a human review step, broaden the labelled benchmark, test adversarial obfuscation, and obtain an independent privacy/security review.

## Tests

Run `pytest -q tests/test_redaction.py` to exercise pattern coverage and verify that the analyzer passes redacted text to the provider adapter.

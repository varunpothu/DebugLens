# Provider input redaction

DebugLens applies a deterministic text-pattern redaction pass to issue/context text sent to a configured external vision provider and source/report/findings text sent to the patch-suggestion provider. Because screenshot pixels are not redacted, external vision-provider calls are now **disabled by default** until an operator explicitly sets `ALLOW_UNREDACTED_SCREENSHOTS=true` after reviewing and approving that data transfer. This is a consent gate, not image redaction.

## What is covered

The helper in `app/redaction.py` masks common patterns for:
- Email addresses and common UK National Insurance number shapes.
- Values attached to labels such as `password`, `secret`, `api_key`, `access_token`, and `authorization`, including quoted values containing spaces.
- Entire values for structured fields whose keys identify sensitive data, such as `password`, `user_email`, `access_token`, or `card_number`.
- Bearer tokens, common GitHub/GitLab tokens, AWS access-key IDs, JWT-shaped strings, private-key blocks, and payment-card-shaped digit sequences.

The pass runs in `app/services/analyzer.py` immediately before vision analysis and recursively redacts string values in the JSON payload built by `app/patch_suggester.py` before patch-suggestion requests. The locally returned analysis retains the user's original issue text; this feature is intended to reduce outbound disclosure, not to rewrite local records.

## Important limitations

- Pattern matching is not a data-loss-prevention guarantee. It can miss novel token formats, obfuscated values, identifiers in other countries, and secrets embedded in arbitrary encodings.
- When `ALLOW_UNREDACTED_SCREENSHOTS=true`, screenshot bytes are sent to the selected vision provider unchanged. Text visible inside screenshots is **not** OCR-scanned or redacted by this feature. The opt-in does not make the image safe; use synthetic/redacted images and obtain privacy approval first.
- Without that setting, non-mock vision analysis fails closed with HTTP 403 before the provider adapter receives the image.
- Source code and findings passed through the patch-suggestion JSON payload are pattern-scanned as text, but browser DOM, logs, HAR files, and arbitrary data outside those provider payloads are not comprehensively scrubbed by this helper.
- A value may be masked even when it is not sensitive, especially long digit sequences.
- Provider retention, training, residency, and contractual settings must be reviewed separately before real user data is sent.

## Operating guidance

1. Keep `ALLOW_UNREDACTED_SCREENSHOTS` unset by default. Prefer synthetic or intentionally redacted screenshots and issue reports.
2. Set `ALLOW_UNREDACTED_SCREENSHOTS=true` only after an operator has approved sending the unredacted image to the configured provider; this flag records an explicit operator choice, not a guarantee of privacy.
3. Do not submit credentials, production user data, or regulated data until a privacy review approves the data flow.
4. Keep provider calls disabled in local tests; CI tests use a mocked provider.
5. Treat redaction as one control among upload validation, access control, retention, logging minimisation, and provider-side privacy settings.
6. Before production, add OCR-assisted image redaction with a human review step, broaden the labelled benchmark, test adversarial obfuscation, and obtain an independent privacy/security review.

## Tests

Run `pytest -q tests/test_redaction.py` to exercise pattern coverage and verify that the analyzer passes redacted text to the provider adapter.

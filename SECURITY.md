# Security policy

## Supported scope

Only the latest commit on the default branch is supported while DebugLens remains an early-stage engineering prototype. It is intended for local development and synthetic or redacted screenshots, not public production use.

## Reporting a vulnerability

Please do not open a public issue containing exploit details, credentials, private screenshots, customer data, or internal URLs. Contact the repository owner privately through GitHub's security reporting feature if enabled for this repository. If private reporting is unavailable, request a private contact route without including the vulnerability details.

Include the affected version/commit, a concise impact description, reproducible steps using synthetic data, and any suggested mitigation. Do not access, alter, or exfiltrate other people's data while validating a finding.

## Current security limitations

- The API supports a configurable shared bearer token, but not user identity, role-based authorisation, or tenant isolation.
- The API has no built-in rate limiting or abuse detection.
- Browser capture is disabled by default. Exact hostname validation must be combined with worker/container network egress controls to defend against SSRF and DNS rebinding.
- Vision providers receive uploaded screenshots when configured. Automatic PII redaction is not implemented.
- Patch proposals are stored, not applied. Test outcomes are reviewer-reported, not executed or independently verified by DebugLens.
- The included Terraform provisions a private artifact bucket only. It is not a complete production deployment.

Do not expose the service to the public internet or send confidential screenshots to an external provider until these limitations have been addressed and reviewed.

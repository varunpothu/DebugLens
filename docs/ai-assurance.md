# AI ethics, assurance, and governance

## Purpose and intended use

DebugLens assists engineers with UI defect investigation. It is a decision-support system, not an autonomous release authority. Its output may be incomplete or wrong and must be independently verified before changing code or systems.

## Out-of-scope uses

- Autonomous deployment, production mutation, or repository merge without explicit human approval.
- Security-sensitive decisions based only on screenshot interpretation.
- Processing sensitive personal data without a documented lawful basis, data minimisation, and approved provider terms.
- Using model confidence as a substitute for evidence or calibrated performance.
- Treating generated tests as proof of correctness without checking that tests detect the target defect.

## Governance mapped to AI risk management

### Govern

- Assign an accountable owner for each model/provider and workflow capability.
- Maintain a model inventory with provider, model ID, release date, prompt version, intended use, known limitations, and approval status.
- Require review before enabling a new provider, tool, target domain, or code-execution capability.
- Maintain an incident log, change history, data-retention policy, and rollback procedure.

### Map

- Identify users, affected developers, application owners, end users, and third-party providers.
- Document expected benefits, foreseeable harms, data flows, trust boundaries, and environmental constraints.
- Assess risks from false positives, missed defects, hallucinated causes, prompt injection, privacy leakage, automation bias, and inaccessible UI recommendations.
- Record the consequence of a wrong finding and choose review depth proportional to risk.

### Measure

- Evaluate against a versioned, representative, consented benchmark.
- Measure precision/recall by defect type, localisation quality, evidence support, confidence calibration, false positives, latency, cost, and reviewer override rates.
- Run adversarial tests for malicious text embedded in screenshots, contradictory evidence, malformed outputs, provider outages, and unsupported claims.
- Report sample size and uncertainty. Model agreement is not ground truth.
- Keep a model card and dataset datasheet describing limitations, provenance, exclusions, and known performance gaps.

### Manage

- Gate high-severity findings, low-confidence outputs, and all code-changing actions for human review.
- Require evidence links for every root-cause claim and record what would falsify the hypothesis.
- Apply bounded retries, deadlines, token/cost budgets, schema validation, and fail-closed behaviour.
- Disable a provider or tool quickly when quality or safety thresholds regress.
- Reassess risk after model, prompt, dependency, data, or infrastructure changes.

## Human oversight design

Reviewers should see the screenshot digest, issue statement, observed evidence, hypotheses, confidence, limitations, proposed tests, and exact patch diff. They must be able to reject a hypothesis, request more evidence, cancel a run, and inspect test results. Approval must bind to the exact patch digest and target environment, not a vague conversation state.

## Privacy and data governance

- Prefer synthetic screenshots and local test applications.
- Send the minimum necessary image/context to a provider.
- Disclose which provider receives the data and obtain required organisational approval.
- Do not log raw screenshots, full DOM text, auth headers, cookies, or provider keys.
- Set retention/deletion periods for screenshots, reports, browser traces, and non-current object versions.
- Document data residency, subprocessors, contractual terms, access controls, and incident notification requirements before production use.
- Provide a deletion workflow and verify that derived artefacts are covered by the same policy.

## Assurance case template

For each release, maintain a claim-evidence record:

| Claim | Evidence required | Release condition |
|---|---|---|
| Upload handling is safe | Malformed-image tests, size/pixel tests, dependency scan | No unresolved high-severity parser findings |
| Findings are evidence-backed | Human-reviewed benchmark and evidence-support metric | Agreed thresholds met by defect class |
| Confidence is meaningful | Calibration report and uncertainty analysis | No material calibration regression |
| Tools are bounded | Permission tests, URL allow-list tests, egress controls | No unauthorised target or tool access |
| Repairs are controlled | Patch-digest approval and isolated test logs | No unapproved code change or release |
| Sensitive data is protected | Data-flow review, retention test, log scan | No unapproved data sharing or exposure |
| Service is operable | SLOs, alert tests, rollback and incident rehearsal | Recovery objectives demonstrated |

## Current assurance status

The repository currently has documented principles, a threat model, typed outputs, provider response validation, target URL validation, workflow transition checks, and CI. It does not yet have a labelled benchmark, automatic image redaction, full tool-permission enforcement, durable audit storage, production egress controls, or a production incident process. Those are release blockers for any production deployment.

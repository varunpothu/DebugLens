# Agentic workflow design

## Specialist roles

1. **Perception agent:** describes visible UI elements and candidate anomaly regions. It may not assert a root cause without supporting signals.
2. **Evidence correlator:** aligns screenshot observations with DOM, console, network, browser version, viewport, and build metadata.
3. **Diagnosis agent:** proposes ranked hypotheses and records what evidence would falsify each one.
4. **Reproduction planner:** converts the leading hypothesis into bounded, repeatable browser steps. Browser access is allow-listed and sandboxed.
5. **Test planner:** proposes regression and accessibility tests. Generated tests require review.
6. **Repair proposer:** prepares a patch diff with rationale, risk, and rollback plan. It cannot merge or deploy.
7. **Verifier:** runs the approved test suite and visual comparison in an isolated worker and records raw pass/fail outcomes.
8. **Assurance reviewer:** checks evidence sufficiency, confidence, privacy, unsafe actions, and required human approvals.

## Orchestration policy

- Pass typed, minimal task payloads between roles, not unbounded chat histories.
- Each task has a deadline, maximum attempts, maximum output size, and cost/token budget.
- Use idempotency keys for external side effects and preserve failed attempts in the audit record.
- Treat screenshots, source files, DOM text, logs, and model outputs as untrusted data.
- No agent may grant itself new tools, alter approval policy, access secrets, or broaden target domains.
- Conflicting model opinions become an explicit uncertainty record, not a forced consensus.
- Escalate low confidence, high severity, missing evidence, and any production-facing action to a human.

## Approval gates

- Gate A: approve the target application and permitted test environment.
- Gate B: approve reproduction steps if they could affect data or external systems.
- Gate C: approve the exact patch digest before tests that execute modified code.
- Gate D: approve repository change or release after required checks pass.

The current repository implements the state machine and provider contracts, not the agents themselves. Agent execution, browser access, and patch handling remain disabled until sandbox and policy enforcement are implemented and tested.

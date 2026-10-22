"""Streamlit dashboard for durable DebugLens investigations and human review."""

import json
import os

import requests
import streamlit as st

st.set_page_config(page_title="DebugLens", page_icon="🔎", layout="wide")
st.title("🔎 DebugLens")
st.caption("Evidence-first UI debugging. Review every finding before acting on it.")

api_url = st.sidebar.text_input("API base URL", os.getenv("DEBUGLENS_API_URL", "http://127.0.0.1:8000")).rstrip("/")
api_token = st.sidebar.text_input("API bearer token (optional)", value=os.getenv("DEBUGLENS_API_TOKEN", ""), type="password")
API_HEADERS = {"Authorization": f"Bearer {api_token}"} if api_token else {}
st.sidebar.info("Use synthetic or redacted screenshots. External vision providers may receive screenshot content when explicitly configured and permitted.")
if st.sidebar.button("Check API health"):
    try:
        response = requests.get(f"{api_url}/health", timeout=5)
        response.raise_for_status()
        st.sidebar.success("API is reachable.")
    except requests.RequestException:
        st.sidebar.error("API is unavailable.")

LEGAL_NEXT_STATES = {
    "human_review": ["reproduced", "rejected", "cancelled"],
    "reproduced": ["rejected", "failed", "cancelled"],
    "patch_proposed": ["rejected", "failed", "cancelled"],
    "tested": ["verified", "rejected", "failed", "cancelled"],
    "received": ["validated", "failed", "cancelled"],
    "validated": ["evidence_collected", "failed", "cancelled"],
    "evidence_collected": ["hypotheses_ready", "failed", "cancelled"],
    "hypotheses_ready": ["human_review", "failed", "cancelled"],
    "verified": [],
    "rejected": [],
    "failed": [],
    "cancelled": [],
}


def api_get(path: str, *, timeout: int = 15) -> dict:
    response = requests.get(f"{api_url}{path}", headers=API_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def api_post(path: str, **kwargs) -> dict:
    response = requests.post(f"{api_url}{path}", headers=API_HEADERS, timeout=90, **kwargs)
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"API returned {response.status_code}: {detail}")
    return response.json()


new_tab, history_tab, review_tab, ensemble_tab = st.tabs(["New investigation", "Run history", "Human review", "Multi-model ensemble"])

with new_tab:
    st.subheader("Create an investigation")
    with st.form("create_run_form"):
        uploaded = st.file_uploader("Screenshot", type=["png", "jpg", "jpeg", "webp"])
        report = st.text_area(
            "What went wrong?",
            max_chars=4000,
            placeholder="Describe expected behaviour, actual behaviour, and steps to reproduce.",
        )
        context = st.text_area(
            "Environment context (optional JSON)",
            placeholder='{"browser":"Chrome","viewport":"390x844","build":"local"}',
        )
        submitted = st.form_submit_button("Analyse and save investigation", type="primary", disabled=uploaded is None)

    if submitted and uploaded is not None:
        data = {"bug_report": report}
        if context.strip():
            try:
                json.loads(context)
            except json.JSONDecodeError:
                st.error("Environment context must be valid JSON.")
                st.stop()
            data["context_json"] = context
        files = {"screenshot": (uploaded.name, uploaded.getvalue(), uploaded.type or "image/png")}
        try:
            with st.spinner("Validating screenshot, analysing, and saving the audit trail..."):
                run = api_post("/v1/debug-runs", data=data, files=files)
            st.success("Investigation saved and moved to human review.")
            st.code(run["workflow_id"])
            if run["analysis"].get("provider") == "mock":
                st.warning("Mock mode does not interpret screenshot pixels. Configure a vision provider for actual visual analysis.")
            st.json(run["analysis"])
            st.download_button(
                "Download analysis JSON",
                json.dumps(run["analysis"], indent=2),
                file_name=f"debuglens-{run['workflow_id']}.json",
                mime="application/json",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(str(exc))

with history_tab:
    st.subheader("Recent investigations")
    if st.button("Refresh history"):
        st.rerun()
    try:
        runs = api_get("/v1/debug-runs?limit=50").get("runs", [])
        if not runs:
            st.info("No investigations yet. Create one in the New investigation tab.")
        else:
            rows = [
                {
                    "Workflow ID": run["workflow_id"],
                    "State": run["state"],
                    "Created": run["created_at"],
                    "Issue": run.get("bug_report") or "(no issue description)",
                    "Provider": run["analysis"].get("provider", "unknown"),
                }
                for run in runs
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
    except (requests.RequestException, RuntimeError) as exc:
        st.error(f"Could not load run history: {exc}")

with review_tab:
    st.subheader("Review an investigation")
    workflow_id = st.text_input("Workflow ID")
    if st.button("Load investigation", type="primary", disabled=not workflow_id.strip()):
        try:
            st.session_state["debuglens_loaded_run"] = api_get(f"/v1/debug-runs/{workflow_id.strip()}")
        except (requests.RequestException, RuntimeError) as exc:
            st.error(f"Could not load investigation: {exc}")

    run = st.session_state.get("debuglens_loaded_run")
    if run:
        st.markdown(f"**Current state:** {run['state']}")
        st.markdown(f"**Issue:** {run.get('bug_report') or 'Not provided'}")
        st.markdown(f"**Screenshot SHA-256:** {run['screenshot_sha256']}")
        st.subheader("Analysis findings")
        st.json(run["analysis"].get("findings", []))
        if run.get("browser_evidence"):
            st.subheader("Browser evidence")
            st.json(run["browser_evidence"])
        with st.expander("Collect approved browser evidence"):
            st.caption("The API must have browser capture enabled and the target hostname must be allow-listed by the operator.")
            with st.form("browser_capture_form"):
                target_url = st.text_input("Approved test page URL", placeholder="https://your-approved-test-host.example/")
                browser_actor = st.text_input("Capture requested by", value="local-reviewer", max_chars=120)
                viewport_width = st.number_input("Viewport width", min_value=320, max_value=3840, value=1440)
                viewport_height = st.number_input("Viewport height", min_value=320, max_value=2160, value=900)
                capture_submitted = st.form_submit_button("Capture browser evidence")
            if capture_submitted:
                try:
                    updated = api_post(
                        f"/v1/debug-runs/{run['workflow_id']}/browser-evidence",
                        json={
                            "target_url": target_url,
                            "actor": browser_actor,
                            "viewport_width": int(viewport_width),
                            "viewport_height": int(viewport_height),
                        },
                    )
                    st.session_state["debuglens_loaded_run"] = updated
                    st.success("Browser evidence attached. Raw browser screenshot was not retained.")
                    st.rerun()
                except (requests.RequestException, RuntimeError) as exc:
                    st.error(f"Browser evidence was not collected: {exc}")
        st.subheader("Investigation pipeline")
        st.json(run["analysis"].get("investigation_pipeline", {}))

        if run["state"] in {"reproduced", "patch_proposed"}:
            st.subheader("Propose or revise a patch")
            st.warning("DebugLens stores a proposal only. It never applies or executes a patch.")
            with st.expander("Generate AI-assisted patch suggestion"):
                st.warning("The source context and issue report will be sent to the configured model provider. Do not submit secrets or confidential source code without approval.")
                with st.form("ai_patch_suggestion_form"):
                    target_file = st.text_input("Repository-relative target file", placeholder="src/components/button.css")
                    source_context = st.text_area("Relevant source context", height=220, max_chars=50000)
                    suggestion_actor = st.text_input("Suggestion requested by", value="local-reviewer", max_chars=120)
                    ai_suggestion_submitted = st.form_submit_button("Generate and save review-only suggestion")
                if ai_suggestion_submitted:
                    try:
                        updated = api_post(
                            f"/v1/debug-runs/{run['workflow_id']}/patch-suggestions",
                            json={
                                "target_file": target_file,
                                "source_context": source_context,
                                "actor": suggestion_actor,
                            },
                        )
                        st.session_state["debuglens_loaded_run"] = updated
                        st.success("AI-assisted patch proposal saved. Review the diff before any use.")
                        st.rerun()
                    except (requests.RequestException, RuntimeError) as exc:
                        st.error(f"Patch suggestion was not generated: {exc}")

            with st.expander("Submit a manually prepared diff"):
                with st.form("patch_proposal_form"):
                    patch_diff = st.text_area("Unified diff", height=240, max_chars=200000)
                    rationale = st.text_area("Why this change should fix the issue", max_chars=3000)
                    risk = st.selectbox("Risk", ["low", "medium", "high", "critical"])
                    rollback_plan = st.text_area("Rollback plan", max_chars=2000)
                    patch_actor = st.text_input("Proposed by", value="local-reviewer", max_chars=120)
                    patch_submitted = st.form_submit_button("Save manual patch proposal")
                if patch_submitted:
                    try:
                        updated = api_post(
                            f"/v1/debug-runs/{run['workflow_id']}/patch-proposals",
                            json={
                                "patch_diff": patch_diff,
                                "rationale": rationale,
                                "risk": risk,
                                "rollback_plan": rollback_plan,
                                "actor": patch_actor,
                            },
                        )
                        st.session_state["debuglens_loaded_run"] = updated
                        st.success("Patch proposal saved and bound to its SHA-256 digest.")
                        st.rerun()
                    except (requests.RequestException, RuntimeError) as exc:
                        st.error(f"Patch proposal was not saved: {exc}")

        proposal = run.get("patch_proposal")
        if proposal:
            st.subheader("Current patch proposal")
            st.code(proposal["patch_diff"], language="diff")
            st.write({"SHA-256": proposal["patch_sha256"], "Risk": proposal["risk"], "Author": proposal["actor"]})
            st.write(proposal["rationale"])
            st.write("Rollback plan: " + proposal["rollback_plan"])
            if run["state"] in {"patch_proposed", "tested"}:
                st.subheader("Record test results")
                st.caption("Run the command yourself in an isolated environment. This form records your reported result; it does not execute the command.")
                with st.form("test_result_form"):
                    test_outcome = st.selectbox("Outcome", ["passed", "failed"])
                    test_command = st.text_input("Command executed", value="pytest -q", max_chars=500)
                    test_summary = st.text_area("Test output summary", max_chars=2000)
                    test_actor = st.text_input("Tested by", value="local-reviewer", max_chars=120)
                    test_submitted = st.form_submit_button("Record test result")
                if test_submitted:
                    try:
                        updated = api_post(
                            f"/v1/debug-runs/{run['workflow_id']}/test-results",
                            json={
                                "patch_sha256": proposal["patch_sha256"],
                                "outcome": test_outcome,
                                "command": test_command,
                                "summary": test_summary,
                                "actor": test_actor,
                            },
                        )
                        st.session_state["debuglens_loaded_run"] = updated
                        st.success("Test result recorded against the exact patch digest.")
                        st.rerun()
                    except (requests.RequestException, RuntimeError) as exc:
                        st.error(f"Test result was not recorded: {exc}")
            if run.get("test_reports"):
                st.subheader("Recorded test reports")
                st.dataframe(run["test_reports"], use_container_width=True, hide_index=True)

        execution_reports = run.get("execution_reports", [])
        if execution_reports:
            st.subheader("Trusted isolated execution reports")
            st.dataframe(
                [
                    {
                        "Suite": report.get("suite"),
                        "Outcome": report.get("outcome"),
                        "Exit code": report.get("exit_code"),
                        "Timed out": report.get("timed_out"),
                        "Duration (s)": report.get("duration_seconds"),
                        "Patch SHA-256": report.get("patch_sha256"),
                        "Workspace SHA-256": report.get("workspace_sha256"),
                        "Actor": report.get("actor"),
                        "Recorded": report.get("created_at"),
                    }
                    for report in execution_reports
                ],
                use_container_width=True,
                hide_index=True,
            )
            for index, report in enumerate(execution_reports, start=1):
                with st.expander(f"Execution output {index}: {report.get('suite', 'unknown suite')}"):
                    st.caption("Output is bounded by the worker. Review it for secrets before sharing.")
                    st.code(str(report.get("output") or "")[:4000], language="text")
                    if report.get("output_truncated"):
                        st.warning("The worker truncated the output; this is not the complete log.")

        st.subheader("Audit history")
        st.dataframe(run["events"], use_container_width=True, hide_index=True)

        choices = LEGAL_NEXT_STATES.get(run["state"], [])
        if choices:
            with st.form("transition_form"):
                target = st.selectbox("Next state", choices)
                actor = st.text_input("Reviewer / actor", value="local-reviewer", max_chars=120)
                reason = st.text_area("Reason and evidence", max_chars=1000)
                transition_submitted = st.form_submit_button("Record transition")
            if transition_submitted:
                if not actor.strip() or not reason.strip():
                    st.error("Actor and reason are required.")
                else:
                    try:
                        updated = api_post(
                            f"/v1/debug-runs/{run['workflow_id']}/transitions",
                            json={"target": target, "actor": actor, "reason": reason},
                        )
                        st.session_state["debuglens_loaded_run"] = updated
                        st.success(f"Workflow moved to {updated['state']}.")
                        st.rerun()
                    except (requests.RequestException, RuntimeError) as exc:
                        st.error(f"Transition was not recorded: {exc}")
        else:
            st.info("This run is in a terminal state. No further transitions are allowed.")



with ensemble_tab:
    st.subheader("Compare vision models")
    st.caption("Runs each selected provider explicitly. Agreement is not ground truth, and minority findings are retained.")
    st.warning(
        "A real vision provider may receive screenshot pixels. The API blocks this by default unless the operator "
        "has explicitly enabled external image transfer after a privacy review. Use synthetic or redacted images."
    )
    with st.form("ensemble_analysis_form"):
        ensemble_image = st.file_uploader(
            "Screenshot for model comparison",
            type=["png", "jpg", "jpeg", "webp"],
            key="ensemble_screenshot",
        )
        ensemble_report = st.text_area(
            "Bug report for every model",
            max_chars=4000,
            key="ensemble_bug_report",
            placeholder="Describe the same expected and actual behaviour for all selected models.",
        )
        ensemble_providers = st.multiselect(
            "Providers to compare",
            options=["mock", "openai_compatible", "anthropic", "gemini"],
            default=["mock"],
            help="Use two or more configured providers for a comparison. Each real provider may incur cost.",
        )
        ensemble_submitted = st.form_submit_button(
            "Compare selected models",
            type="primary",
            disabled=ensemble_image is None or not ensemble_providers,
        )

    if ensemble_submitted and ensemble_image is not None:
        files = {
            "screenshot": (
                ensemble_image.name,
                ensemble_image.getvalue(),
                ensemble_image.type or "image/png",
            )
        }
        data = {
            "bug_report": ensemble_report,
            "providers": ",".join(ensemble_providers),
        }
        try:
            with st.spinner("Running selected providers and comparing findings..."):
                report = api_post("/v1/ensemble-analyses", data=data, files=files)
            st.metric("Providers completed", report["providers_completed"])
            st.metric("Providers failed", report["providers_failed"])
            st.metric("Uncorroborated finding clusters", report["unresolved_disagreement_count"])
            if report["providers_failed"]:
                st.warning("At least one provider failed. A failure is not evidence that the screenshot has no defects.")
            st.subheader("Finding clusters")
            if report["finding_clusters"]:
                for cluster in report["finding_clusters"]:
                    with st.expander(
                        f"{cluster['cluster_id']} · {cluster['agreement_label']} · "
                        f"{cluster['supporting_provider_count']} provider(s)"
                    ):
                        st.json(cluster)
            else:
                st.info("No findings were returned. Check provider status and remember that absence of findings is not proof of a clean UI.")
            st.subheader("Per-provider results")
            st.json(report["provider_runs"])
            st.subheader("Assurance and limitations")
            st.json(report["assurance"])
            st.write(report["limitations"])
            st.download_button(
                "Download ensemble report",
                json.dumps(report, indent=2),
                file_name="debuglens-ensemble-report.json",
                mime="application/json",
            )
        except (requests.RequestException, RuntimeError) as exc:
            st.error(f"Ensemble analysis failed: {exc}")

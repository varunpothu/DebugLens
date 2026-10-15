"""Streamlit dashboard for durable DebugLens investigations and human review."""

import json

import requests
import streamlit as st

st.set_page_config(page_title="DebugLens", page_icon="🔎", layout="wide")
st.title("🔎 DebugLens")
st.caption("Evidence-first UI debugging. Review every finding before acting on it.")

api_url = st.sidebar.text_input("API base URL", "http://127.0.0.1:8000").rstrip("/")
st.sidebar.info("Use synthetic or redacted screenshots. The API is for trusted local development only.")
if st.sidebar.button("Check API health"):
    try:
        response = requests.get(f"{api_url}/health", timeout=5)
        response.raise_for_status()
        st.sidebar.success("API is reachable.")
    except requests.RequestException:
        st.sidebar.error("API is unavailable.")

LEGAL_NEXT_STATES = {
    "human_review": ["reproduced", "rejected", "cancelled"],
    "reproduced": ["patch_proposed", "rejected", "failed", "cancelled"],
    "patch_proposed": ["tested", "rejected", "failed", "cancelled"],
    "tested": ["verified", "patch_proposed", "rejected", "failed", "cancelled"],
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
    response = requests.get(f"{api_url}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def api_post(path: str, **kwargs) -> dict:
    response = requests.post(f"{api_url}{path}", timeout=90, **kwargs)
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"API returned {response.status_code}: {detail}")
    return response.json()


new_tab, history_tab, review_tab = st.tabs(["New investigation", "Run history", "Human review"])

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

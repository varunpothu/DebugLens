"""Optional local Streamlit client for DebugLens."""

import json

import requests
import streamlit as st

st.set_page_config(page_title="DebugLens", page_icon="🔎", layout="wide")
st.title("🔎 DebugLens")
st.caption("Evidence-first screenshot debugging. Findings in mock mode are intentionally non-diagnostic.")
api_url = st.sidebar.text_input("API base URL", "http://127.0.0.1:8000").rstrip("/")
st.sidebar.info("Use synthetic or redacted screenshots. Do not upload secrets or customer data.")

uploaded = st.file_uploader("Upload a screenshot", type=["png", "jpg", "jpeg", "webp"])
report = st.text_area("What went wrong?", max_chars=4000, placeholder="Describe expected and actual behaviour...")
context = st.text_area("Optional context JSON", placeholder='{"browser":"Chrome","viewport":"390x844"}')

if st.button("Analyse screenshot", type="primary", disabled=uploaded is None):
    files = {"screenshot": (uploaded.name, uploaded.getvalue(), uploaded.type or "image/png")}
    data = {"bug_report": report}
    if context.strip():
        try:
            json.loads(context)
        except json.JSONDecodeError:
            st.error("Context must be valid JSON.")
            st.stop()
        data["context_json"] = context
    try:
        with st.spinner("Validating and analysing..."):
            response = requests.post(f"{api_url}/v1/analyses", files=files, data=data, timeout=60)
        if response.ok:
            result = response.json()
            st.success(f"Analysis {result['analysis_id']} completed")
            st.warning("Mock mode validates the file but does not interpret screenshot pixels. Do not treat this as a diagnosis.")
            st.json(result)
            st.download_button("Download analysis JSON", json.dumps(result, indent=2), file_name="debuglens-analysis.json", mime="application/json")
        else:
            st.error(f"API returned {response.status_code}: {response.text[:1000]}")
    except requests.RequestException as exc:
        st.error(f"Could not reach the API: {exc}")

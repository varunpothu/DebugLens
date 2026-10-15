import hashlib
import hmac
import json
from hashlib import sha256
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (20, 10), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Correlation-ID" in response.headers


def test_readiness_endpoint() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["analysis_provider"] == "mock"


def test_analysis_endpoint_returns_structured_result() -> None:
    response = client.post(
        "/v1/analyses",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={"bug_report": "Layout breaks on narrow viewport"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["screenshot_width"] == 20
    assert payload["screenshot_height"] == 10
    assert payload["human_review_required"] is True
    assert payload["findings"]


def test_analysis_rejects_wrong_mime_type() -> None:
    response = client.post(
        "/v1/analyses",
        files={"screenshot": ("screen.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_analysis_rejects_invalid_image_bytes() -> None:
    response = client.post(
        "/v1/analyses",
        files={"screenshot": ("screen.png", b"invalid", "image/png")},
    )
    assert response.status_code == 422


def test_analysis_rejects_invalid_context_json() -> None:
    response = client.post(
        "/v1/analyses",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={"context_json": "{broken"},
    )
    assert response.status_code == 400



def test_analysis_includes_validated_environment_context() -> None:
    response = client.post(
        "/v1/analyses",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={
            "bug_report": "Button is clipped",
            "context_json": '{"browser":"Chromium","viewport":"390x844"}',
        },
    )
    assert response.status_code == 200
    report = response.json()["bug_report"]
    assert "Button is clipped" in report
    assert "Environment context (untrusted data)" in report
    assert '"viewport":"390x844"' in report


def test_debug_run_endpoint_persists_audit_trail_and_supports_review() -> None:
    created = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={"bug_report": "Primary button overlaps the footer"},
    )
    assert created.status_code == 200
    run = created.json()
    assert run["state"] == "human_review"
    assert run["analysis"]["provider"] == "mock"
    assert len(run["events"]) == 4
    workflow_id = run["workflow_id"]

    fetched = client.get(f"/v1/debug-runs/{workflow_id}")
    assert fetched.status_code == 200
    assert fetched.json()["workflow_id"] == workflow_id

    transitioned = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={
            "target": "reproduced",
            "actor": "local-reviewer",
            "reason": "Reproduced on the test page at 390x844 viewport",
        },
    )
    assert transitioned.status_code == 200
    assert transitioned.json()["state"] == "reproduced"
    assert transitioned.json()["events"][-1]["actor"] == "local-reviewer"


def test_debug_run_rejects_illegal_transition() -> None:
    created = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
    )
    workflow_id = created.json()["workflow_id"]
    response = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={"target": "verified", "actor": "reviewer", "reason": "Attempt to skip testing"},
    )
    assert response.status_code == 409


def test_debug_run_rejects_invalid_context() -> None:
    response = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={"context_json": "not-json"},
    )
    assert response.status_code == 400



def test_patch_proposal_and_test_result_api_enforce_digest_gate(monkeypatch) -> None:
    created = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={"bug_report": "Button overflows its container"},
    )
    workflow_id = created.json()["workflow_id"]
    reproduced = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={
            "target": "reproduced",
            "actor": "reviewer",
            "reason": "Reproduced at a 390x844 viewport.",
        },
    )
    assert reproduced.status_code == 200

    patch_diff = "diff --git a/app.css b/app.css\n-old\n+fixed"
    proposal = client.post(
        f"/v1/debug-runs/{workflow_id}/patch-proposals",
        json={
            "patch_diff": patch_diff,
            "rationale": "Constrain the button to its parent container.",
            "risk": "low",
            "rollback_plan": "Revert the CSS change.",
            "actor": "reviewer",
        },
    )
    assert proposal.status_code == 200
    digest = sha256(patch_diff.encode("utf-8")).hexdigest()
    assert proposal.json()["patch_proposal"]["patch_sha256"] == digest

    wrong_digest = client.post(
        f"/v1/debug-runs/{workflow_id}/test-results",
        json={
            "patch_sha256": "0" * 64,
            "outcome": "passed",
            "command": "pytest -q",
            "summary": "All tests passed.",
            "actor": "reviewer",
        },
    )
    assert wrong_digest.status_code == 409

    passed = client.post(
        f"/v1/debug-runs/{workflow_id}/test-results",
        json={
            "patch_sha256": digest,
            "outcome": "passed",
            "command": "pytest -q",
            "summary": "Regression test passed in the local fixture.",
            "actor": "reviewer",
        },
    )
    assert passed.status_code == 200
    assert passed.json()["state"] == "tested"

    blocked = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={
            "target": "verified",
            "actor": "reviewer",
            "reason": "Manual reports are not independent execution evidence.",
        },
    )
    assert blocked.status_code == 409

    monkeypatch.setattr("app.main.settings.execution_signing_secret", "test-signing-secret-that-is-long-enough-32")
    payload = {
        "workflow_id": workflow_id,
        "patch_sha256": digest,
        "suite": "pytest",
        "outcome": "passed",
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 1.25,
        "workspace_sha256": "a" * 64,
        "output": "5 passed",
        "output_truncated": False,
        "actor": "trusted-runner",
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(
        b"test-signing-secret-that-is-long-enough-32", body, hashlib.sha256
    ).hexdigest()
    execution = client.post(
        f"/v1/debug-runs/{workflow_id}/execution-results",
        content=body,
        headers={"Content-Type": "application/json", "X-DebugLens-Signature": signature},
    )
    assert execution.status_code == 200
    assert execution.json()["execution_reports"][0]["workspace_sha256"] == "a" * 64

    verified = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={
            "target": "verified",
            "actor": "reviewer",
            "reason": "Reviewed the exact diff and trusted execution report.",
        },
    )
    assert verified.status_code == 200
    assert verified.json()["state"] == "verified"


def test_browser_evidence_endpoint_is_disabled_by_default() -> None:
    created = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
    )
    response = client.post(
        f"/v1/debug-runs/{created.json()['workflow_id']}/browser-evidence",
        json={
            "target_url": "https://example.org/",
            "actor": "reviewer",
            "viewport_width": 1440,
            "viewport_height": 900,
        },
    )
    assert response.status_code == 404



def test_configured_bearer_token_protects_api_routes(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.api_access_token", "test-token")
    denied = client.get("/v1/debug-runs")
    assert denied.status_code == 401
    allowed = client.get("/v1/debug-runs", headers={"Authorization": "Bearer test-token"})
    assert allowed.status_code == 200
    health = client.get("/health")
    assert health.status_code == 200



def test_patch_suggestion_requires_configured_provider() -> None:
    created = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", png_bytes(), "image/png")},
        data={"bug_report": "Button overflows"},
    )
    workflow_id = created.json()["workflow_id"]
    reproduced = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={
            "target": "reproduced",
            "actor": "reviewer",
            "reason": "Reproduced on a local fixture.",
        },
    )
    assert reproduced.status_code == 200
    response = client.post(
        f"/v1/debug-runs/{workflow_id}/patch-suggestions",
        json={
            "target_file": "app.css",
            "source_context": ".button { width: 118%; }",
            "actor": "reviewer",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Patch suggestion failed or the configured provider is unavailable."

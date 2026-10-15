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

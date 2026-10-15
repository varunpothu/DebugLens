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

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.main import app

client = TestClient(app)


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 8), "white").save(output, format="PNG")
    return output.getvalue()


def test_non_local_audit_events_use_server_configured_actor(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "staging")
    monkeypatch.setattr(main.settings, "api_access_token", "a" * 32)
    monkeypatch.setattr(main.settings, "api_service_actor", "debuglens-service")
    headers = {"Authorization": f"Bearer {main.settings.api_access_token}"}

    created = client.post(
        "/v1/debug-runs",
        files={"screenshot": ("screen.png", _png_bytes(), "image/png")},
        headers=headers,
    )
    assert created.status_code == 200
    workflow_id = created.json()["workflow_id"]

    transitioned = client.post(
        f"/v1/debug-runs/{workflow_id}/transitions",
        json={
            "target": "reproduced",
            "actor": "spoofed-administrator",
            "reason": "Reproduced using the synthetic fixture.",
        },
        headers=headers,
    )
    assert transitioned.status_code == 200
    assert transitioned.json()["events"][-1]["actor"] == "debuglens-service"

    proposal = client.post(
        f"/v1/debug-runs/{workflow_id}/patch-proposals",
        json={
            "patch_diff": "diff --git a/app.css b/app.css\n--- a/app.css\n+++ b/app.css\n@@ -1 +1 @@\n-old\n+new",
            "rationale": "Synthetic test patch.",
            "risk": "low",
            "rollback_plan": "Revert the one-file diff.",
            "actor": "spoofed-owner",
        },
        headers=headers,
    )
    assert proposal.status_code == 200
    patch_event = next(
        event for event in proposal.json()["events"] if event["event_type"] == "patch_proposal_created"
    )
    assert patch_event["actor"] == "debuglens-service"


def test_local_audit_actor_remains_explicit_for_development(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "local")
    monkeypatch.setattr(main.settings, "api_service_actor", "debuglens-service")
    assert main._resolve_audit_actor("local-reviewer") == "local-reviewer"

import pytest
from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_configured_api_token_protects_private_routes(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_access_token", "test-only-token")

    assert client.get("/v1/debug-runs").status_code == 401
    assert client.get(
        "/v1/debug-runs",
        headers={"Authorization": "Bearer wrong-token"},
    ).status_code == 401

    authorized = client.get(
        "/v1/debug-runs",
        headers={"Authorization": "Bearer test-only-token"},
    )
    assert authorized.status_code == 200
    assert "runs" in authorized.json()


def test_health_endpoint_remains_public_when_token_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "api_access_token", "test-only-token")
    response = client.get("/health")
    assert response.status_code == 200


def test_production_rejects_short_api_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "production")
    monkeypatch.setattr(main.settings, "api_access_token", "too-short")
    with pytest.raises(RuntimeError, match="at least 32 non-whitespace characters"):
        main.validate_startup_configuration()


def test_local_mode_allows_empty_api_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "local")
    monkeypatch.setattr(main.settings, "api_access_token", "")
    main.validate_startup_configuration()

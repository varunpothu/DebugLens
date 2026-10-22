from __future__ import annotations

from typing import Any

from app.deployment_policy import validate_compose_config


def service(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ports": [],
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "privileged": False,
        "network_mode": "bridge",
        "mem_limit": "128m",
        "pids_limit": 64,
        "networks": {"app": {}},
        "environment": {},
    }
    base.update(overrides)
    return base


def valid_config() -> dict[str, Any]:
    return {
        "services": {
            "api": service(environment={
                "API_ACCESS_TOKEN": "synthetic-test-token",
                "BROWSER_ENABLED": "false",
                "ALLOW_UNREDACTED_SCREENSHOTS": "false",
            }),
            "ui": service(environment={
                "DEBUGLENS_LOCKED_CONFIG": "true",
                "DEBUGLENS_API_TOKEN": "synthetic-test-token",
            }),
            "auth": service(environment={
                "OAUTH2_PROXY_COOKIE_SECURE": "true",
                "OAUTH2_PROXY_COOKIE_HTTPONLY": "true",
                "OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL": "false",
            }),
            "proxy": service(
                ports=[
                    {"target": 80, "published": "80", "protocol": "tcp"},
                    {"target": 443, "published": "443", "protocol": "tcp"},
                    {"target": 443, "published": "443", "protocol": "udp"},
                ],
                cap_add=["NET_BIND_SERVICE"],
            ),
        }
    }


def test_valid_private_aws_compose_has_no_policy_violations() -> None:
    assert validate_compose_config(valid_config()) == []


def test_rejects_public_api_port_and_enabled_browser_capture() -> None:
    config = valid_config()
    config["services"]["api"]["ports"] = [{"target": 8000, "published": "8000", "protocol": "tcp"}]
    config["services"]["api"]["environment"]["BROWSER_ENABLED"] = "true"

    errors = validate_compose_config(config)

    assert any("must not publish host ports" in error for error in errors)
    assert any("Browser capture must remain disabled" in error for error in errors)


def test_rejects_insecure_proxy_and_unexpected_public_port() -> None:
    config = valid_config()
    config["services"]["proxy"]["read_only"] = False
    config["services"]["proxy"]["ports"].append(
        {"target": 8501, "published": "8501", "protocol": "tcp"}
    )

    errors = validate_compose_config(config)

    assert any("reverse proxy must use a read-only" in error for error in errors)
    assert any("Only HTTP 80/tcp" in error for error in errors)


def test_rejects_missing_token_and_insecure_auth_cookies() -> None:
    config = valid_config()
    config["services"]["api"]["environment"]["API_ACCESS_TOKEN"] = ""
    config["services"]["auth"]["environment"]["OAUTH2_PROXY_COOKIE_SECURE"] = "false"

    errors = validate_compose_config(config)

    assert any("API_ACCESS_TOKEN must be configured" in error for error in errors)
    assert any("OAUTH2_PROXY_COOKIE_SECURE must be enabled" in error for error in errors)

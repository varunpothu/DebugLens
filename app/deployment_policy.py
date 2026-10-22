"""Static policy checks for the rendered AWS Docker Compose configuration."""
from __future__ import annotations

from typing import Any


def validate_compose_config(config: dict[str, Any]) -> list[str]:
    """Return policy violations for a resolved Compose configuration."""
    errors: list[str] = []
    services = config.get("services")
    if not isinstance(services, dict):
        return ["Compose configuration must contain a services object."]

    for name in ("api", "ui", "auth"):
        service = services.get(name)
        if not isinstance(service, dict):
            errors.append(f"Required service '{name}' is missing.")
            continue
        if service.get("ports"):
            errors.append(f"Service '{name}' must not publish host ports.")
        if service.get("read_only") is not True:
            errors.append(f"Service '{name}' must use a read-only root filesystem.")
        if "ALL" not in service.get("cap_drop", []):
            errors.append(f"Service '{name}' must drop all Linux capabilities.")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            errors.append(f"Service '{name}' must enable no-new-privileges.")
        if service.get("privileged") is True:
            errors.append(f"Service '{name}' must not run privileged.")
        if service.get("network_mode") == "host":
            errors.append(f"Service '{name}' must not use host networking.")
        if not service.get("mem_limit") or not service.get("pids_limit"):
            errors.append(f"Service '{name}' must define memory and PID limits.")
        networks = service.get("networks") or {}
        network_names = set(networks) if isinstance(networks, dict) else set(networks)
        if "app" not in network_names:
            errors.append(f"Service '{name}' must use the private app network.")

    api = services.get("api", {})
    api_env = api.get("environment", {}) if isinstance(api, dict) else {}
    if isinstance(api_env, dict):
        if api_env.get("BROWSER_ENABLED") != "false":
            errors.append("Browser capture must remain disabled in the AWS pilot.")
        if str(api_env.get("ALLOW_UNREDACTED_SCREENSHOTS", "")).lower() != "false":
            errors.append("External screenshot transfer must remain opt-in and disabled.")
        if not api_env.get("API_ACCESS_TOKEN"):
            errors.append("API_ACCESS_TOKEN must be configured.")

    ui = services.get("ui", {})
    ui_env = ui.get("environment", {}) if isinstance(ui, dict) else {}
    if isinstance(ui_env, dict):
        if ui_env.get("DEBUGLENS_LOCKED_CONFIG") != "true":
            errors.append("The deployed UI must lock API configuration.")
        if not ui_env.get("DEBUGLENS_API_TOKEN"):
            errors.append("The UI must receive its backend API token.")

    auth = services.get("auth", {})
    auth_env = auth.get("environment", {}) if isinstance(auth, dict) else {}
    if isinstance(auth_env, dict):
        for variable in ("OAUTH2_PROXY_COOKIE_SECURE", "OAUTH2_PROXY_COOKIE_HTTPONLY"):
            if auth_env.get(variable) != "true":
                errors.append(f"{variable} must be enabled.")
        if auth_env.get("OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL") != "false":
            errors.append("Unverified OIDC email addresses must not be accepted.")

    proxy = services.get("proxy")
    if not isinstance(proxy, dict):
        errors.append("Required service 'proxy' is missing.")
    else:
        if proxy.get("read_only") is not True:
            errors.append("The reverse proxy must use a read-only root filesystem.")
        if "ALL" not in proxy.get("cap_drop", []):
            errors.append("The reverse proxy must drop all Linux capabilities.")
        if "NET_BIND_SERVICE" not in proxy.get("cap_add", []):
            errors.append("The reverse proxy may add only NET_BIND_SERVICE.")
        if "no-new-privileges:true" not in proxy.get("security_opt", []):
            errors.append("The reverse proxy must enable no-new-privileges.")
        if proxy.get("privileged") is True or proxy.get("network_mode") == "host":
            errors.append("The reverse proxy must not use privileged mode or host networking.")
        if not proxy.get("mem_limit") or not proxy.get("pids_limit"):
            errors.append("The reverse proxy must define memory and PID limits.")
        proxy_networks = proxy.get("networks") or {}
        proxy_network_names = set(proxy_networks) if isinstance(proxy_networks, dict) else set(proxy_networks)
        if "app" not in proxy_network_names:
            errors.append("The reverse proxy must use the app network.")
        ports = {
            (int(item.get("target", 0)), item.get("protocol", "tcp"))
            for item in proxy.get("ports", [])
            if isinstance(item, dict)
        }
        if ports != {(80, "tcp"), (443, "tcp"), (443, "udp")}:
            errors.append("Only HTTP 80/tcp and HTTPS 443/tcp+udp may be published.")

    return errors

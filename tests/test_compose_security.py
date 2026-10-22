from pathlib import Path


def test_compose_api_port_is_bound_to_loopback_only() -> None:
    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose = compose_file.read_text(encoding="utf-8")
    assert '"127.0.0.1:8000:8000"' in compose
    assert '"8000:8000"' not in compose


def test_compose_keeps_browser_capture_disabled_by_default() -> None:
    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose = compose_file.read_text(encoding="utf-8")
    assert 'BROWSER_ENABLED: "false"' in compose

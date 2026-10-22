import pytest

from app import main


def test_local_environment_allows_empty_token_for_development(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "local")
    monkeypatch.setattr(main.settings, "api_access_token", "")
    main.validate_startup_configuration()


def test_non_local_environment_rejects_missing_or_weak_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "staging")
    for token in ("", "short", " " * 40):
        monkeypatch.setattr(main.settings, "api_access_token", token)
        with pytest.raises(RuntimeError, match="outside local/development/test"):
            main.validate_startup_configuration()


def test_non_local_environment_accepts_strong_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "staging")
    monkeypatch.setattr(main.settings, "api_access_token", "a" * 32)
    main.validate_startup_configuration()


def test_test_environment_allows_empty_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "app_env", "test")
    monkeypatch.setattr(main.settings, "api_access_token", "")
    main.validate_startup_configuration()



def test_interactive_api_docs_are_enabled_only_for_local_environments() -> None:
    for environment in ("local", "development", "test"):
        assert main._docs_enabled_for_environment(environment) is True
    for environment in ("staging", "production", "prod", "preview"):
        assert main._docs_enabled_for_environment(environment) is False

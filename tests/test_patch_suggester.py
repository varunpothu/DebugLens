import json

import pytest

from app.config import Settings
from app.patch_suggester import _parse_suggestion, suggest_patch, validate_target_file


def valid_payload() -> dict[str, str]:
    return {
        "patch_diff": (
            "diff --git a/app.css b/app.css\n"
            "--- a/app.css\n"
            "+++ b/app.css\n"
            "@@ -1 +1 @@\n"
            "-.button { width: 118%; }\n"
            "+.button { max-width: 100%; }"
        ),
        "rationale": "Prevent the button from exceeding its parent.",
        "risk": "low",
        "rollback_plan": "Revert the one-file CSS diff.",
    }


def test_validate_target_file_rejects_traversal_and_absolute_paths() -> None:
    assert validate_target_file("src/components/button.css") == "src/components/button.css"
    for path in (
        "../secret.txt", "/etc/passwd", "C:\\temp\\secret.txt", ".git/config",
        "src/../secret.txt", "src//secret.txt", "src/./secret.txt",
        "src/file.css\n+++ b/secrets.txt", "src/file.css\x00",
    ):
        with pytest.raises(ValueError):
            validate_target_file(path)


def test_parse_suggestion_accepts_one_target_file_only() -> None:
    result = _parse_suggestion(
        json.dumps(valid_payload()),
        "app.css",
        "openai_compatible",
        "test-model",
    )
    assert result.provider == "openai_compatible"
    assert result.risk == "low"
    assert result.patch_diff.startswith("diff --git a/app.css b/app.css")


def test_parse_suggestion_rejects_unrelated_file_diff() -> None:
    payload = valid_payload()
    payload["patch_diff"] = payload["patch_diff"].replace("a/app.css b/app.css", "a/other.css b/other.css")
    with pytest.raises(ValueError, match="requested target file"):
        _parse_suggestion(json.dumps(payload), "app.css", "openai_compatible", "test-model")


def test_parse_suggestion_rejects_multiple_file_and_binary_diffs() -> None:
    payload = valid_payload()
    payload["patch_diff"] += (
        "\n--- a/secrets.txt\n+++ b/secrets.txt\n@@ -1 +1 @@\n-secret\n+leaked"
    )
    with pytest.raises(ValueError, match="exactly one"):
        _parse_suggestion(json.dumps(payload), "app.css", "openai_compatible", "test-model")

    payload = valid_payload()
    payload["patch_diff"] += "\nGIT binary patch"
    with pytest.raises(ValueError, match="text-only"):
        _parse_suggestion(json.dumps(payload), "app.css", "openai_compatible", "test-model")


def test_parse_suggestion_rejects_invalid_risk() -> None:
    payload = valid_payload()
    payload["risk"] = "certain"
    with pytest.raises(ValueError, match="invalid risk"):
        _parse_suggestion(json.dumps(payload), "app.css", "openai_compatible", "test-model")


class FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.body


class FakeClient:
    last_payload: dict[str, object] | None = None

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, *args: object, **kwargs: object) -> FakeResponse:
        payload = kwargs.get("json")
        if isinstance(payload, dict):
            FakeClient.last_payload = payload
        return FakeResponse({
            "choices": [{"message": {"content": json.dumps(valid_payload())}}],
        })


def test_suggest_patch_uses_explicit_provider_and_returns_review_only_diff(monkeypatch) -> None:
    monkeypatch.setattr("app.patch_suggester.httpx.Client", FakeClient)
    settings = Settings(
        analysis_provider="openai_compatible",
        vision_api_key="test-key",
        vision_model="test-model",
        vision_base_url="https://example.test/v1",
    )
    result = suggest_patch(
        settings=settings,
        target_file="app.css",
        source_context=".button { width: 118%; }",
        bug_report="Button overflows at mobile viewport.",
        findings=[],
    )
    assert result.patch_diff.startswith("diff --git")
    assert result.provider == "openai_compatible"
    assert result.model == "test-model"


def test_suggest_patch_fails_closed_without_provider_credentials() -> None:
    settings = Settings(analysis_provider="openai_compatible")
    with pytest.raises(RuntimeError, match="credentials"):
        suggest_patch(
            settings=settings,
            target_file="app.css",
            source_context=".button { width: 118%; }",
            bug_report="Button overflows",
            findings=[],
        )


def test_suggest_patch_redacts_source_report_and_findings_before_provider(monkeypatch) -> None:
    monkeypatch.setattr("app.patch_suggester.httpx.Client", FakeClient)
    FakeClient.last_payload = None
    settings = Settings(
        analysis_provider="openai_compatible",
        vision_api_key="test-key",
        vision_model="test-model",
        vision_base_url="https://example.test/v1",
    )
    suggest_patch(
        settings=settings,
        target_file="app.css",
        source_context="Maintainer alex@example.com; password=source-secret-value",
        bug_report="api_key: sk-example-secret",
        findings=[{"summary": "access_token=private-token-value"}],
    )

    assert FakeClient.last_payload is not None
    messages = FakeClient.last_payload["messages"]
    assert isinstance(messages, list)
    user_content = messages[1]["content"]
    assert isinstance(user_content, str)
    payload = json.loads(user_content)
    assert "alex@example.com" not in payload["source_context"]
    assert "source-secret-value" not in payload["source_context"]
    assert "sk-example-secret" not in payload["bug_report"]
    assert "private-token-value" not in payload["findings"][0]["summary"]
    assert "[REDACTED]" in payload["source_context"]

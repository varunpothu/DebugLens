from io import BytesIO
import json

import pytest
from PIL import Image

from app.providers.base import ImageInput
from app.providers.native_vision import AnthropicVisionProvider, GeminiVisionProvider
from app.providers.openai_compatible import OpenAICompatibleVisionProvider


def image_input() -> ImageInput:
    stream = BytesIO()
    Image.new("RGB", (12, 10), "white").save(stream, format="PNG")
    return ImageInput(
        content=stream.getvalue(),
        media_type="image/png",
        sha256="a" * 64,
        width=12,
        height=10,
    )


def finding_payload() -> dict[str, object]:
    return {
        "findings": [{
            "title": "Possible alignment issue",
            "severity": "low",
            "confidence": 0.4,
            "category": "layout",
            "summary": "A visual alignment issue may be present.",
            "evidence": [{
                "source": "screenshot",
                "description": "The element appears misaligned in the provided image.",
                "observed": True,
            }],
            "hypotheses": ["A responsive layout rule may be involved."],
            "recommended_checks": ["Compare at a second viewport."],
        }]
    }


class FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._body


class FakeClient:
    def __init__(self, *, timeout: float, body: dict[str, object]) -> None:
        self.body = body
        self.timeout = timeout

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, *args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(self.body)


@pytest.mark.parametrize("provider_name", ["openai_compatible", "anthropic", "gemini"])
def test_provider_adapters_parse_structured_findings(monkeypatch, provider_name: str) -> None:
    payload_text = json.dumps(finding_payload())
    if provider_name == "openai_compatible":
        body = {"id": "response-1", "choices": [{"message": {"content": payload_text}}], "usage": {}}
        monkeypatch.setattr(
            "app.providers.openai_compatible.httpx.Client",
            lambda timeout: FakeClient(timeout=timeout, body=body),
        )
        provider = OpenAICompatibleVisionProvider(
            api_key="test-key", model="test-vision-model", base_url="https://example.test/v1"
        )
    elif provider_name == "anthropic":
        body = {"id": "message-1", "content": [{"type": "text", "text": payload_text}], "usage": {}}
        monkeypatch.setattr(
            "app.providers.native_vision.httpx.Client",
            lambda timeout: FakeClient(timeout=timeout, body=body),
        )
        provider = AnthropicVisionProvider(api_key="test-key", model="test-vision-model")
    else:
        body = {
            "candidates": [{"content": {"parts": [{"text": payload_text}]}}],
            "usageMetadata": {},
        }
        monkeypatch.setattr(
            "app.providers.native_vision.httpx.Client",
            lambda timeout: FakeClient(timeout=timeout, body=body),
        )
        provider = GeminiVisionProvider(api_key="test-key", model="test-vision-model")

    result = provider.analyse(image_input(), "Button appears misaligned")
    assert result.provider == provider_name
    assert result.model == "test-vision-model"
    assert result.prompt_version == {
        "openai_compatible": "openai-compatible-ui-v1",
        "anthropic": "anthropic-ui-v1",
        "gemini": "gemini-ui-v1",
    }[provider_name]
    assert len(result.findings) == 1
    assert result.findings[0].category == "layout"

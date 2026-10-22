"""Native provider adapters for Anthropic Messages and Google Gemini APIs."""
from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.providers.base import ImageInput, ProviderResult
from app.providers.openai_compatible import SYSTEM_PROMPT

ANTHROPIC_PROMPT_VERSION = "anthropic-ui-v1"
GEMINI_PROMPT_VERSION = "gemini-ui-v1"
from app.schemas import Finding


def _parse_findings(text: str) -> list[Finding]:
    payload = json.loads(text)
    items = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Model response must contain a findings array.")
    return [Finding.model_validate(item) for item in items]


class AnthropicVisionProvider:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 45.0):
        if not api_key.strip() or not model.strip():
            raise ValueError("An Anthropic API key and model name are required.")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def analyse(self, image: ImageInput, bug_report: str | None) -> ProviderResult:
        import base64

        prompt = (
            "Inspect this UI screenshot. Return JSON only with a findings array. "
            "Do not claim DOM/runtime evidence not supplied. "
            f"Dimensions: {image.width}x{image.height}. Bug report: {bug_report or 'None'}"
        )
        payload = {
            "model": self._model,
            "max_tokens": 1800,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.b64encode(image.content).decode("ascii"),
                }},
            ]}],
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            text_blocks = [item.get("text", "") for item in body.get("content", []) if item.get("type") == "text"]
            findings = _parse_findings("\n".join(text_blocks))
            usage = body.get("usage") or {}
            return ProviderResult(
                provider=self.name,
                model=self._model,
                findings=findings,
                raw_response_id=body.get("id"),
                usage_input_tokens=usage.get("input_tokens"),
                usage_output_tokens=usage.get("output_tokens"),
                prompt_version=ANTHROPIC_PROMPT_VERSION,
            )
        except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise RuntimeError("Anthropic vision request failed or returned invalid structured output.") from exc


class GeminiVisionProvider:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 45.0):
        if not api_key.strip() or not model.strip():
            raise ValueError("A Gemini API key and model name are required.")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def analyse(self, image: ImageInput, bug_report: str | None) -> ProviderResult:
        import base64

        prompt = (
            f"{SYSTEM_PROMPT}\nInspect this screenshot. Return JSON only. "
            f"Dimensions: {image.width}x{image.height}. Bug report: {bug_report or 'None'}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [
                {"text": prompt},
                {"inlineData": {
                    "mimeType": image.media_type,
                    "data": base64.b64encode(image.content).decode("ascii"),
                }},
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers={"x-goog-api-key": self._api_key}, json=payload)
                response.raise_for_status()
                body = response.json()
            candidates = body.get("candidates") or []
            text = candidates[0]["content"]["parts"][0]["text"]
            findings = _parse_findings(text)
            usage = body.get("usageMetadata") or {}
            return ProviderResult(
                provider=self.name,
                model=self._model,
                findings=findings,
                raw_response_id=None,
                usage_input_tokens=usage.get("promptTokenCount"),
                usage_output_tokens=usage.get("candidatesTokenCount"),
                prompt_version=GEMINI_PROMPT_VERSION,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise RuntimeError("Gemini vision request failed or returned invalid structured output.") from exc

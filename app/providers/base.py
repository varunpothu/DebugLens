"""Provider-neutral contract for multimodal analysis adapters."""

from dataclasses import dataclass
from typing import Protocol

from app.schemas import Finding


@dataclass(frozen=True, slots=True)
class ImageInput:
    content: bytes
    media_type: str
    sha256: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider: str
    model: str
    findings: list[Finding]
    raw_response_id: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None


class VisionProvider(Protocol):
    """A provider must return validated findings and disclose its identity."""

    @property
    def name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def analyse(self, image: ImageInput, bug_report: str | None) -> ProviderResult: ...

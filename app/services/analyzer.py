"""Analysis orchestration with explicit provider selection and a transparent mock mode."""
from hashlib import sha256
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.providers.base import ImageInput, ProviderResult, VisionProvider
from app.redaction import redact_sensitive_text
from app.providers.native_vision import AnthropicVisionProvider, GeminiVisionProvider
from app.providers.openai_compatible import OpenAICompatibleVisionProvider
from app.schemas import AnalysisResponse, Evidence, Finding, Severity


class InvalidImageError(ValueError):
    """Raised when uploaded bytes are not a valid supported image."""


def inspect_image(image_bytes: bytes) -> tuple[str, int, int, str]:
    """Decode an image safely and return its digest, dimensions, and normalised MIME type."""
    if not image_bytes:
        raise InvalidImageError("The uploaded image is empty.")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            if image_format not in {"PNG", "JPEG", "WEBP"}:
                raise InvalidImageError("Supported image formats are PNG, JPEG, and WEBP.")
            image.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > 40_000_000:
                raise InvalidImageError("Image dimensions are invalid or exceed the pixel limit.")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("The upload is not a valid image.") from exc
    assert image_format is not None
    media_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image_format]
    return sha256(image_bytes).hexdigest(), width, height, media_type


def _run_vision_provider(
    provider: str,
    image_bytes: bytes,
    digest: str,
    width: int,
    height: int,
    media_type: str,
    bug_report: str | None,
) -> ProviderResult:
    settings = get_settings()
    image = ImageInput(
        content=image_bytes,
        media_type=media_type,
        sha256=digest,
        width=width,
        height=height,
    )
    adapter: VisionProvider
    if provider == "openai_compatible":
        if not settings.vision_api_key or not settings.vision_model:
            raise RuntimeError("Vision provider credentials or model configuration are missing.")
        adapter = OpenAICompatibleVisionProvider(
            api_key=settings.vision_api_key,
            model=settings.vision_model,
            base_url=settings.vision_base_url,
            timeout_seconds=settings.vision_timeout_seconds,
        )
    elif provider == "anthropic":
        if not settings.anthropic_api_key or not settings.anthropic_model:
            raise RuntimeError("Anthropic provider credentials or model configuration are missing.")
        adapter = AnthropicVisionProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout_seconds=settings.vision_timeout_seconds,
        )
    elif provider == "gemini":
        if not settings.gemini_api_key or not settings.gemini_model:
            raise RuntimeError("Gemini provider credentials or model configuration are missing.")
        adapter = GeminiVisionProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.vision_timeout_seconds,
        )
    else:
        raise RuntimeError(f"Provider '{provider}' is not supported.")
    return adapter.analyse(image, bug_report)


def analyse_screenshot(
    image_bytes: bytes,
    bug_report: str | None,
    provider: str = "mock",
) -> AnalysisResponse:
    """Validate evidence, call the explicitly selected provider, and return a typed result."""
    digest, width, height, media_type = inspect_image(image_bytes)
    if provider == "mock":
        findings = [
            Finding(
                title="Visual inspection required",
                severity=Severity.INFO,
                confidence=0.0,
                category="analysis_limit",
                summary=(
                    "The image was validated and fingerprinted, but mock mode does not inspect "
                    "visual content. No defect has been confirmed. Configure an approved vision "
                    "provider or attach browser/runtime evidence to continue the investigation."
                ),
                evidence=[
                    Evidence(
                        source="upload_validator",
                        description=f"Decoded image successfully ({width}x{height}); SHA-256 recorded.",
                        observed=True,
                    )
                ],
                hypotheses=[],
                recommended_checks=[
                    "Reproduce the issue at the reported viewport and browser version.",
                    "Capture console errors, failed network requests, and relevant DOM state.",
                    "Compare the screenshot against an approved baseline if one exists.",
                ],
            )
        ]
        provider_version = "baseline-1"
    else:
        result = _run_vision_provider(
            provider, image_bytes, digest, width, height, media_type, redact_sensitive_text(bug_report)
        )
        findings = result.findings
        provider_version = result.model

    plan = [
        "Confirm the expected behaviour and exact reproduction steps.",
        "Record browser, operating system, viewport, device scale factor, and build identifier.",
        "Capture console errors and failed network requests without collecting secrets.",
        "Reproduce in an isolated test environment and preserve a minimal failing case.",
        "After diagnosis, add a regression test before proposing a repair.",
    ]
    limitations = [
        "Screenshot-only analysis cannot establish runtime or DOM root causes without additional evidence.",
        "No browser automation, code modification, or execution was performed.",
        "Findings require human review and additional evidence before action.",
    ]
    if provider == "mock":
        limitations.insert(0, "Mock provider does not perform visual reasoning or infer defects from pixels.")
    return AnalysisResponse(
        provider=provider,
        provider_version=provider_version,
        screenshot_sha256=digest,
        screenshot_width=width,
        screenshot_height=height,
        bug_report=bug_report,
        findings=findings,
        test_plan=plan,
        limitations=limitations,
    )

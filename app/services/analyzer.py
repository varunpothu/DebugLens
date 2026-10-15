"""Analysis provider abstraction and deterministic local implementation.

Mock mode deliberately does not claim to interpret image pixels. It returns a transparent
baseline and demonstrates the response contract until a reviewed vision adapter is configured.
"""

from hashlib import sha256
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.schemas import AnalysisResponse, Evidence, Finding, Severity


class InvalidImageError(ValueError):
    """Raised when uploaded bytes are not a valid supported image."""


def inspect_image(image_bytes: bytes) -> tuple[str, int, int]:
    """Decode an image safely and return its digest and dimensions."""
    if not image_bytes:
        raise InvalidImageError("The uploaded image is empty.")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise InvalidImageError("Supported image formats are PNG, JPEG, and WEBP.")
            image.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > 40_000_000:
                raise InvalidImageError("Image dimensions are invalid or exceed the pixel limit.")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("The upload is not a valid image.") from exc
    return sha256(image_bytes).hexdigest(), width, height


def analyse_screenshot(
    image_bytes: bytes,
    bug_report: str | None,
    provider: str = "mock",
) -> AnalysisResponse:
    """Create a safe baseline analysis; real providers must implement this contract explicitly."""
    digest, width, height = inspect_image(image_bytes)
    if provider != "mock":
        raise RuntimeError(
            f"Provider '{provider}' is not installed. Configure an explicit reviewed adapter."
        )

    findings = [
        Finding(
            title="Visual inspection required",
            severity=Severity.INFO,
            confidence=0.0,
            category="analysis_limit",
            summary=(
                "The image was validated and fingerprinted, but mock mode does not inspect "
                "visual content. No defect has been confirmed. Connect an approved vision "
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
    plan = [
        "Confirm the expected behaviour and exact reproduction steps.",
        "Record browser, operating system, viewport, device scale factor, and build identifier.",
        "Capture console errors and failed network requests without collecting secrets.",
        "Reproduce in an isolated test environment and preserve a minimal failing case.",
        "After diagnosis, add a regression test before proposing a repair.",
    ]
    return AnalysisResponse(
        provider="mock",
        provider_version="baseline-1",
        screenshot_sha256=digest,
        screenshot_width=width,
        screenshot_height=height,
        bug_report=bug_report,
        findings=findings,
        test_plan=plan,
        limitations=[
            "Mock provider does not perform visual reasoning or infer defects from pixels.",
            "No browser automation, code modification, or execution was performed.",
            "Findings require human review and additional evidence before action.",
        ],
    )

"""Stable API contracts for analysis and evidence."""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    observed: bool = True
    location: str | None = Field(default=None, max_length=250)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    category: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=30)
    hypotheses: list[str] = Field(default_factory=list, max_length=10)
    recommended_checks: list[str] = Field(default_factory=list, max_length=20)


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "completed"
    provider: str
    provider_version: str
    screenshot_sha256: str
    screenshot_width: int = Field(gt=0)
    screenshot_height: int = Field(gt=0)
    bug_report: str | None = None
    findings: list[Finding]
    test_plan: list[str]
    limitations: list[str]
    human_review_required: bool = True


class ReadinessResponse(BaseModel):
    status: str
    app: str
    environment: str
    analysis_provider: str



class TransitionRequest(BaseModel):
    """Human-attributed workflow transition request."""

    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=40)
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)



class BrowserCaptureRequest(BaseModel):
    """Explicit browser capture request; enabled only for approved hostnames."""

    model_config = ConfigDict(extra="forbid")
    target_url: str = Field(min_length=8, max_length=2048)
    actor: str = Field(min_length=1, max_length=120)
    viewport_width: int = Field(default=1440, ge=320, le=3840)
    viewport_height: int = Field(default=900, ge=320, le=2160)

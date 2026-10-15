"""FastAPI entry point for DebugLens."""

import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.schemas import AnalysisResponse, ReadinessResponse
from app.services.analyzer import InvalidImageError, analyse_screenshot

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("debuglens")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("DebugLens starting; provider=%s", settings.analysis_provider)
    yield
    logger.info("DebugLens shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Evidence-first screenshot debugging and verification API.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Correlation-ID"],
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Correlation-ID", str(uuid4()))[:100]
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness endpoint; contains no secrets or infrastructure details."""
    return {"status": "ok"}


@app.get("/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    """Readiness endpoint reports configured mode without exposing credentials."""
    return ReadinessResponse(
        status="ready",
        app=settings.app_name,
        environment=settings.app_env,
        analysis_provider=settings.analysis_provider,
    )


@app.post("/v1/analyses", response_model=AnalysisResponse)
async def create_analysis(
    screenshot: UploadFile = File(...),
    bug_report: str | None = Form(default=None, max_length=4000),
    context_json: str | None = Form(default=None, max_length=12000),
) -> AnalysisResponse:
    """Validate a screenshot and return an evidence-oriented analysis result."""
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if screenshot.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WEBP image.")
    raw = await screenshot.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Screenshot exceeds the upload size limit.")
    if context_json:
        try:
            context = json.loads(context_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="context_json must be valid JSON.") from exc
        if not isinstance(context, dict):
            raise HTTPException(status_code=400, detail="context_json must be a JSON object.")
    try:
        return analyse_screenshot(raw, bug_report, settings.analysis_provider)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("Analysis provider unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Configured analysis provider is unavailable.") from exc

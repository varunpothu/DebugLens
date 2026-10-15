"""FastAPI entry point for DebugLens."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.agents import build_investigation_pipeline
from app.config import get_settings
from app.schemas import (
    AnalysisResponse,
    BrowserCaptureRequest,
    PatchProposalRequest,
    ReadinessResponse,
    TestResultRequest,
    TransitionRequest,
)
from app.run_store import (
    attach_browser_evidence,
    create_patch_proposal,
    create_run,
    get_run,
    initialise_store,
    list_runs,
    record_test_result,
    transition_run,
)
from app.workflow import WorkflowState
from app.browser.capture import UnsafeTargetError, capture_page
from app.services.analyzer import InvalidImageError, analyse_screenshot

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("debuglens")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("DebugLens starting; provider=%s", settings.analysis_provider)
    initialise_store()
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
async def correlation_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("X-Correlation-ID", str(uuid4()))[:100]
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
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



@app.post("/v1/debug-runs")
async def create_debug_run(
    screenshot: UploadFile = File(...),
    bug_report: str | None = Form(default=None, max_length=4000),
    context_json: str | None = Form(default=None, max_length=12000),
) -> dict:
    """Create a durable local run and move it to human review; no code is changed."""
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if screenshot.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WEBP image.")
    raw = await screenshot.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Screenshot exceeds the upload size limit.")
    context: dict = {}
    if context_json:
        try:
            parsed_context = json.loads(context_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="context_json must be valid JSON.") from exc
        if not isinstance(parsed_context, dict):
            raise HTTPException(status_code=400, detail="context_json must be a JSON object.")
        context = parsed_context
    enriched_report = bug_report
    if context:
        context_summary = json.dumps(context, ensure_ascii=True, separators=(",", ":"))[:3000]
        enriched_report = f"{bug_report or 'No issue description supplied.'}\nEnvironment context (untrusted data): {context_summary}"
    try:
        analysis = analyse_screenshot(raw, enriched_report, settings.analysis_provider)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("Analysis provider unavailable")
        raise HTTPException(status_code=503, detail="Configured analysis provider is unavailable.") from exc
    except Exception as exc:
        logger.exception("Unexpected analysis failure")
        raise HTTPException(status_code=502, detail="Analysis failed; no debugging run was created.") from exc
    try:
        analysis_payload = analysis.model_dump(mode="json")
        analysis_payload["investigation_pipeline"] = build_investigation_pipeline(analysis_payload)
        return create_run(
            bug_report=bug_report,
            screenshot_sha256=analysis.screenshot_sha256,
            analysis=analysis_payload,
        )
    except Exception as exc:
        logger.exception("Could not persist debugging run")
        raise HTTPException(status_code=500, detail="Could not persist debugging run.") from exc


@app.get("/v1/debug-runs")
def get_debug_runs(limit: int = 20) -> dict:
    """List recent debugging runs without returning screenshot bytes."""
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    return {"runs": list_runs(limit=limit)}


@app.get("/v1/debug-runs/{workflow_id}")
def get_debug_run(workflow_id: str) -> dict:
    """Retrieve a debugging run and its audit history."""
    try:
        return get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc


@app.post("/v1/debug-runs/{workflow_id}/transitions")
def transition_debug_run(workflow_id: str, request: TransitionRequest) -> dict:
    """Record a legal, human-attributed workflow transition."""
    try:
        target = WorkflowState(request.target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unknown workflow state.") from exc
    try:
        return transition_run(
            workflow_id,
            target=target,
            actor=request.actor,
            reason=request.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@app.post("/v1/debug-runs/{workflow_id}/browser-evidence")
async def collect_browser_evidence(
    workflow_id: str,
    request: BrowserCaptureRequest,
) -> dict:
    """Capture an allow-listed page in a disposable environment and attach minimised evidence."""
    if not settings.browser_enabled:
        raise HTTPException(
            status_code=404,
            detail="Browser capture is disabled. Enable it only for an approved, isolated environment.",
        )
    if not settings.allowed_browser_hosts:
        raise HTTPException(status_code=503, detail="No browser target allow-list is configured.")
    try:
        run = get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    try:
        capture = await capture_page(
            request.target_url,
            allowed_hosts=settings.allowed_browser_hosts,
            viewport=(request.viewport_width, request.viewport_height),
        )
    except UnsafeTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("Browser capture could not start")
        raise HTTPException(status_code=503, detail="Browser capture is unavailable.") from exc
    except Exception as exc:
        logger.exception("Browser capture failed")
        raise HTTPException(status_code=502, detail="Browser capture failed.") from exc

    try:
        screenshot_analysis = analyse_screenshot(
            capture.screenshot_png,
            run.get("bug_report"),
            settings.analysis_provider,
        )
    except InvalidImageError as exc:
        raise HTTPException(status_code=502, detail="Browser returned an invalid screenshot.") from exc
    except RuntimeError as exc:
        logger.warning("Browser screenshot analysis provider unavailable")
        raise HTTPException(status_code=503, detail="Configured analysis provider is unavailable.") from exc

    evidence = {
        "final_url": capture.final_url,
        "page_title": capture.page_title,
        "viewport_width": capture.viewport_width,
        "viewport_height": capture.viewport_height,
        "dom_tag_counts": capture.dom_tag_counts,
        "console_error_types": capture.console_errors,
        "page_error_types": capture.page_errors,
        "failed_request_count": capture.failed_request_count,
        "screenshot_sha256": screenshot_analysis.screenshot_sha256,
        "screenshot_analysis": screenshot_analysis.model_dump(mode="json"),
        "raw_screenshot_retained": False,
    }
    try:
        pipeline = build_investigation_pipeline(run["analysis"], evidence)
        return attach_browser_evidence(
            workflow_id,
            actor=request.actor,
            evidence=evidence,
            investigation_pipeline=pipeline,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



@app.post("/v1/debug-runs/{workflow_id}/patch-proposals")
def propose_patch(workflow_id: str, request: PatchProposalRequest) -> dict:
    """Store a human-authored patch diff; never applies or executes it."""
    try:
        return create_patch_proposal(
            workflow_id,
            patch_diff=request.patch_diff,
            rationale=request.rationale,
            risk=request.risk,
            rollback_plan=request.rollback_plan,
            actor=request.actor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/debug-runs/{workflow_id}/test-results")
def submit_test_result(workflow_id: str, request: TestResultRequest) -> dict:
    """Record a manually executed test result tied to the exact patch digest."""
    try:
        return record_test_result(
            workflow_id,
            patch_sha256=request.patch_sha256,
            outcome=request.outcome,
            command=request.command,
            summary=request.summary,
            actor=request.actor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

"""FastAPI entry point for DebugLens."""

import hmac
import json
import logging
import re
from hashlib import sha256
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.agents import build_investigation_pipeline
from app.ensemble import compare_ensemble
from app.config import get_settings
from app.schemas import (
    AnalysisResponse,
    BrowserCaptureRequest,
    ExecutionResultRequest,
    PatchProposalRequest,
    PatchSuggestionRequest,
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
    record_execution_result,
    record_test_result,
    transition_run,
)
from app.workflow import WorkflowState
from app.browser.capture import UnsafeTargetError, capture_page
from app.services.analyzer import InvalidImageError, ProviderConsentRequired, analyse_screenshot
from app.patch_suggester import suggest_patch
from app.request_body_limit import RequestBodyLimitMiddleware
from app.rate_limit import InMemoryRateLimiter
from app.providers.budget import ProviderRateLimitError

settings = get_settings()
rate_limiter = InMemoryRateLimiter(
    max_requests=settings.api_rate_limit_requests,
    window_seconds=settings.api_rate_limit_window_seconds,
)
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("debuglens")


def _resolve_audit_actor(requested_actor: str) -> str:
    """Trust request actor labels only in local development; use server identity elsewhere."""
    if settings.app_env.strip().lower() in {"local", "development", "test"}:
        return requested_actor
    return settings.api_service_actor


def validate_startup_configuration() -> None:
    """Fail closed outside local/test environments when the shared API token is weak or missing."""
    environment = settings.app_env.strip().lower()
    local_environments = {"local", "development", "test"}
    if environment not in local_environments and len(settings.api_access_token.strip()) < 32:
        raise RuntimeError(
            "API_ACCESS_TOKEN must contain at least 32 non-whitespace characters "
            "outside local/development/test environments."
        )


def _docs_enabled_for_environment(environment: str) -> bool:
    """Expose interactive API documentation only in trusted local environments."""
    return environment.strip().lower() in {"local", "development", "test"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("DebugLens starting; provider=%s", settings.analysis_provider)
    validate_startup_configuration()
    initialise_store()
    yield
    logger.info("DebugLens shutting down")


docs_enabled = _docs_enabled_for_environment(settings.app_env)
app = FastAPI(
    title=settings.app_name,
    description="Evidence-first screenshot debugging and verification API.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=settings.max_upload_bytes + 1024 * 1024,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Correlation-ID", "Authorization"],
)


def _request_correlation_id(request: Request) -> str:
    """Reuse a safe client correlation ID or generate one without reflecting arbitrary text."""
    existing = getattr(request.state, "debuglens_correlation_id", None)
    if existing:
        return str(existing)
    supplied = request.headers.get("X-Correlation-ID", "")
    request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,100}", supplied) else str(uuid4())
    request.state.debuglens_correlation_id = request_id
    return request_id


def _apply_response_headers(response: Response, request: Request) -> Response:
    """Apply correlation and browser/cache safety headers to successful and rejected responses."""
    response.headers["X-Correlation-ID"] = _request_correlation_id(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def correlation_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    return _apply_response_headers(response, request)


@app.middleware("http")
async def require_api_token(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Protect API operations when a bearer token is configured."""
    public_paths = {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}
    if request.method != "OPTIONS" and request.url.path not in public_paths and settings.api_access_token:
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.api_access_token}"
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(status_code=401, content={"detail": "Valid bearer token required."})
    return await call_next(request)


@app.middleware("http")
async def rate_limit_api_writes(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Bound write/analysis request bursts per client in this process."""
    if request.method == "POST" and request.url.path.startswith("/v1/"):
        client_key = request.client.host if request.client is not None else "unknown"
        allowed, retry_after = rate_limiter.check(client_key)
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many API requests. Retry after the current rate-limit window."},
                headers={"Retry-After": str(retry_after)},
            )
            return _apply_response_headers(response, request)
    return await call_next(request)


@app.middleware("http")
async def request_guardrails(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Reject obviously oversized declared bodies and add conservative API response headers."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            return _apply_response_headers(
                JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."}),
                request,
            )
        if declared_length < 0:
            return _apply_response_headers(
                JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."}),
                request,
            )
        # Allow multipart framing and form fields in addition to the bounded screenshot itself.
        max_request_bytes = settings.max_upload_bytes + 1024 * 1024
        if declared_length > max_request_bytes:
            return _apply_response_headers(
                JSONResponse(status_code=413, content={"detail": "Request body exceeds the configured limit."}),
                request,
            )
    response = await call_next(request)
    return _apply_response_headers(response, request)

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
        enriched_report = (
            f"{bug_report or 'No issue description supplied.'}\n"
            f"Environment context (untrusted data): {context_summary}"
        )
    try:
        return analyse_screenshot(raw, enriched_report, settings.analysis_provider)
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderConsentRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="Provider request budget exhausted. Retry after the current window.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
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
    except ProviderConsentRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="Provider request budget exhausted. Retry after the current window.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
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
            actor=_resolve_audit_actor(request.actor),
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
    if settings.app_env.lower() not in {"local", "development", "test"}:
        raise HTTPException(
            status_code=503,
            detail="Browser capture is restricted to local development until an isolated browser worker is deployed.",
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
    except ProviderConsentRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="Provider request budget exhausted. Retry after the current window.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except RuntimeError as exc:
        logger.warning("Browser screenshot analysis provider unavailable")
        raise HTTPException(status_code=503, detail="Configured analysis provider is unavailable.") from exc

    evidence = {
        "final_url": capture.final_url,
        "page_title": capture.page_title,
        "viewport_width": capture.viewport_width,
        "viewport_height": capture.viewport_height,
        "dom_tag_counts": capture.dom_tag_counts,
        "dom_count_truncated": capture.dom_count_truncated,
        "console_error_types": capture.console_errors,
        "page_error_types": capture.page_errors,
        "failed_request_count": capture.failed_request_count,
        "accessibility_audit": capture.accessibility_report,
        "screenshot_sha256": screenshot_analysis.screenshot_sha256,
        "screenshot_analysis": screenshot_analysis.model_dump(mode="json"),
        "raw_screenshot_retained": False,
    }
    try:
        pipeline = build_investigation_pipeline(run["analysis"], evidence)
        return attach_browser_evidence(
            workflow_id,
            actor=_resolve_audit_actor(request.actor),
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
            actor=_resolve_audit_actor(request.actor),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/debug-runs/{workflow_id}/patch-suggestions")
def generate_patch_suggestion(workflow_id: str, request: PatchSuggestionRequest) -> dict:
    """Generate a review-only patch suggestion from supplied source context."""
    try:
        run = get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    if run["state"] not in {WorkflowState.REPRODUCED.value, WorkflowState.PATCH_PROPOSED.value}:
        raise HTTPException(
            status_code=409,
            detail="A patch suggestion is only allowed after reproduction or during patch revision.",
        )
    try:
        suggestion = suggest_patch(
            settings=settings,
            target_file=request.target_file,
            source_context=request.source_context,
            bug_report=run.get("bug_report"),
            findings=run["analysis"].get("findings", []),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("Patch suggestion provider unavailable")
        raise HTTPException(
            status_code=503,
            detail="Patch suggestion failed or the configured provider is unavailable.",
        ) from exc
    rationale = f"AI-assisted suggestion from {suggestion.provider}/{suggestion.model}. {suggestion.rationale}"
    try:
        return create_patch_proposal(
            workflow_id,
            patch_diff=suggestion.patch_diff,
            rationale=rationale,
            risk=suggestion.risk,
            rollback_plan=suggestion.rollback_plan,
            actor=_resolve_audit_actor(request.actor),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@app.post("/v1/debug-runs/{workflow_id}/execution-results")
async def submit_execution_result(workflow_id: str, request: Request) -> dict:
    """Accept a result signed by the trusted host orchestrator, never by the worker container."""
    secret = settings.execution_signing_secret
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="Trusted execution result ingestion is not configured.",
        )
    raw_body = await request.body()
    supplied_signature = request.headers.get("X-DebugLens-Signature", "")
    expected_signature = hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Valid execution result signature required.")
    try:
        payload = ExecutionResultRequest.model_validate_json(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid execution result payload.") from exc
    if payload.workflow_id != workflow_id:
        raise HTTPException(status_code=422, detail="Workflow ID in payload does not match the URL.")
    try:
        return record_execution_result(
            workflow_id,
            execution_id=payload.execution_id,
            patch_sha256=payload.patch_sha256,
            suite=payload.suite,
            outcome=payload.outcome,
            exit_code=payload.exit_code,
            timed_out=payload.timed_out,
            duration_seconds=payload.duration_seconds,
            workspace_sha256=payload.workspace_sha256,
            output=payload.output,
            output_truncated=payload.output_truncated,
            actor=payload.actor,
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
            actor=_resolve_audit_actor(request.actor),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debugging run not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@app.post("/v1/ensemble-analyses")
async def create_ensemble_analysis(
    screenshot: UploadFile = File(...),
    providers: str = Form(..., max_length=200),
    bug_report: str | None = Form(default=None, max_length=4000),
) -> dict:
    """Compare explicitly selected vision providers while preserving disagreements."""
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if screenshot.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WEBP image.")
    raw = await screenshot.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Screenshot exceeds the upload size limit.")
    selected = [item.strip() for item in providers.split(",") if item.strip()]
    allowed_providers = {"mock", "openai_compatible", "anthropic", "gemini"}
    if not selected or len(selected) > 4 or len(set(selected)) != len(selected):
        raise HTTPException(
            status_code=422,
            detail="Select between one and four unique providers.",
        )
    if any(item not in allowed_providers for item in selected):
        raise HTTPException(
            status_code=422,
            detail="Unsupported provider selected. Allowed providers: mock, openai_compatible, anthropic, gemini.",
        )
    try:
        return compare_ensemble(raw, bug_report, selected)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected ensemble analysis failure")
        raise HTTPException(status_code=502, detail="Ensemble analysis failed.") from exc

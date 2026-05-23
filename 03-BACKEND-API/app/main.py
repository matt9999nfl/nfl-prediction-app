"""
NFL Prediction Platform — Backend API
FastAPI entry point.

Middleware:
  - RequestIDMiddleware: injects a UUID request_id into request.state and the
    response X-Request-ID header.  All error responses include this ID.

Error handling:
  - HTTPException: converted to the standard ErrorResponse envelope.
  - All unhandled exceptions: logged with request_id, returned as 500
    with {"error": ..., "code": "internal_error", "request_id": ...}.
    Raw BigQuery exceptions never leak to clients.

Auth:
  - X-API-Key header is accepted but NOT enforced in Phase 2 (single-user tool).
  - Enforcement is wired in Phase 3.

Out of scope (Phase 2):
  - Rate limiting
  - Write endpoints (POST/PUT/DELETE) — added in Steps 2-4
  - /teams/{team}/ol-rating — deferred to Phase 3
"""
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.routers import datasets, experiments, features, frameworks, games, health, predictions, teams

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


# ── App ───────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="NFL Prediction Platform API",
    version=settings.api_version,
    description=(
        "NFL Prediction Platform API — Phase 2.  "
        "Serves game data, experiment results, predictions, and features (read).  "
        "Accepts dataset uploads and schema mappings (write).  "
        "Steps 3-5: experiment run trigger, framework CRUD, Claude schema inference."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to specific origins once a custom domain is set
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware ────────────────────────────────────────────────────────────────


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request_id to every request; echo it in the response header."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


# ── Exception handlers ────────────────────────────────────────────────────────


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTPException to the standard ErrorResponse envelope."""
    request_id = _request_id(request)
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        # Router already built the full error dict (includes request_id).
        return JSONResponse(status_code=exc.status_code, content=detail)
    # Fallback: wrap plain string detail.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(detail), "code": _status_to_code(exc.status_code), "request_id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to the standard error envelope."""
    request_id = _request_id(request)
    errors = exc.errors()
    # Summarise all field errors into a single human-readable message.
    messages = [f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors]
    return JSONResponse(
        status_code=422,
        content={
            "error": "; ".join(messages),
            "code": "invalid_params",
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all: log the full traceback, return a safe 500 to the client."""
    request_id = _request_id(request)
    logger.error(
        "Unhandled exception [request_id=%s] %s: %s",
        request_id, type(exc).__name__, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred",
            "code": "internal_error",
            "request_id": request_id,
        },
    )


def _status_to_code(status: int) -> str:
    return {
        400: "invalid_params",
        401: "unauthorized",
        404: "not_found",
        409: "conflict",
        422: "invalid_params",
        429: "rate_limited",
        500: "internal_error",
        502: "upstream_error",
        503: "upstream_error",
    }.get(status, "internal_error")


# ── Routers ───────────────────────────────────────────────────────────────────


app.include_router(health.router)
app.include_router(games.router)
app.include_router(experiments.router)
app.include_router(predictions.router)
app.include_router(features.router)
app.include_router(datasets.router)
app.include_router(frameworks.router)
app.include_router(teams.router)


# ── Entry point ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )

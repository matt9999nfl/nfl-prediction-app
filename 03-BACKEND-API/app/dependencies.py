"""
FastAPI dependencies shared across routers.
"""
import base64
import logging

from fastapi import Header, HTTPException, Request
from google.cloud import bigquery

from app.bigquery_client import get_client
from app.config import settings

logger = logging.getLogger(__name__)


# ── Request ID ────────────────────────────────────────────────────────────────


def get_request_id(request: Request) -> str:
    """Read the request_id injected by RequestIDMiddleware."""
    return getattr(request.state, "request_id", "unknown")


# ── BigQuery client ───────────────────────────────────────────────────────────


def get_bq_client() -> bigquery.Client:
    """Dependency that supplies the shared BigQuery client."""
    return get_client()


# ── Cursor-based pagination helpers ──────────────────────────────────────────


def encode_cursor(offset: int) -> str:
    """Encode an integer offset as a URL-safe base64 string."""
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    """Decode a cursor back to an integer offset.  Returns 0 on any error."""
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0


# ── Authentication ───────────────────────────────────────────────────────────


def require_api_key(x_api_key: str = Header(None), request: Request = None) -> None:
    """
    Dependency for write endpoints (POST/PUT/DELETE).

    If OWNER_API_KEY is configured (Phase 3 production mode), validates the
    X-API-Key header. If not configured (dev mode), allows all requests.

    Raises HTTPException(401) if key is missing or invalid in production mode.
    """
    if not settings.owner_api_key:
        # Dev mode: key not configured → open (no-op)
        return

    if x_api_key != settings.owner_api_key:
        # Production mode: key missing or invalid
        request_id = getattr(request.state, "request_id", "") if request else ""
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Missing or invalid API key",
                "code": "unauthorized",
                "request_id": request_id,
            },
        )

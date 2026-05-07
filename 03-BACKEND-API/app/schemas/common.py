"""
Shared response types used across multiple routers.

Matches API_CONTRACTS.md  →  Common Types section.
"""
from pydantic import BaseModel


class Pagination(BaseModel):
    next_cursor: str | None = None
    has_more: bool


class ErrorResponse(BaseModel):
    """Standard error envelope.  All 4xx/5xx responses use this shape."""
    error: str       # human-readable message
    code: str        # machine-readable code (see API_CONTRACTS.md Error Codes table)
    request_id: str

"""GET /health — service liveness check."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["service"])


class HealthResponse(BaseModel):
    status: str
    version: str
    commit: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns 200 when the service is running.  No auth required.",
)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.api_version,
        commit=settings.git_commit,
    )

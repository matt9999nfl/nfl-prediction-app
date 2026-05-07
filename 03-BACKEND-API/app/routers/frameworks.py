"""
Framework endpoints — Step 4.

  POST   /api/v1/frameworks                     — create (201)
  GET    /api/v1/frameworks                     — list (200, paginated)
  GET    /api/v1/frameworks/{framework_id}      — single (200)
  PUT    /api/v1/frameworks/{framework_id}      — update metadata/config (200)
  DELETE /api/v1/frameworks/{framework_id}      — delete (204)

Table: platform.frameworks

POST config sources (enforced by FrameworkCreateRequest):
  - base_experiment_id provided: fetch ExperimentConfig from platform.experiment_configs
    and copy it as the config_snapshot.  404 if experiment not found.
  - config provided directly: build config_snapshot from the caller's payload.
    A synthetic ExperimentConfig is constructed (experiment_id = framework_id,
    status = "draft", gate_passed = null).
  - Neither provided: 400 (caught by Pydantic model_validator before reaching the router).

PUT: updates only the fields that are non-null in the request body.  No side effects
on platform.experiment_configs or experiments.backtest_runs.

DELETE: straight 204 — no reference checks required for frameworks.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from google.cloud import bigquery

from app.config import settings
from app.dependencies import decode_cursor, encode_cursor, get_bq_client, get_request_id
from app.queries import experiments as eq
from app.queries import frameworks as fq
from app.schemas.common import ErrorResponse, Pagination
from app.schemas.experiments import ExperimentConfig
from app.schemas.frameworks import (
    Framework,
    FrameworkCreateRequest,
    FrameworkListResponse,
    FrameworkUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/frameworks", tags=["frameworks"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_config_snapshot_from_create(
    framework_id: str,
    body_config,          # ExperimentCreateRequest
    created_at: str,
) -> dict:
    """
    Build a full ExperimentConfig-compatible dict from a direct-config POST body.
    Uses framework_id as the synthetic experiment_id so the snapshot is self-contained.
    """
    return {
        "experiment_id": framework_id,
        "name":          f"Framework config {framework_id[:8]}",
        "created_at":    created_at,
        "target":        body_config.target,
        "features":      [f.model_dump() for f in body_config.features],
        "evaluation":    body_config.evaluation.model_dump(),
        "methodology":   body_config.methodology.model_dump(),
        "model":         body_config.model.model_dump(),
        "status":        "draft",
        "gate_passed":   None,
    }


# ── POST /api/v1/frameworks ──────────────────────────────────────────────────


@router.post(
    "",
    response_model=Framework,
    status_code=201,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Save an experiment config as a named framework",
)
def create_framework(
    body: FrameworkCreateRequest,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> Framework:
    framework_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Resolve config snapshot ──────────────────────────────────────────────
    if body.base_experiment_id is not None:
        try:
            exp_row = eq.get_experiment_by_id(bq, body.base_experiment_id)
        except Exception as exc:
            logger.error(
                "[%s] BigQuery error fetching experiment %s for framework: %s",
                request_id, body.base_experiment_id, exc, exc_info=True,
            )
            raise HTTPException(
                status_code=502,
                detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
            )

        if exp_row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": f"Experiment '{body.base_experiment_id}' not found",
                    "code": "not_found",
                    "request_id": request_id,
                },
            )
        config_snapshot = exp_row   # already a normalised dict matching ExperimentConfig

    else:
        # body.config is guaranteed non-None by FrameworkCreateRequest validator.
        config_snapshot = _build_config_snapshot_from_create(
            framework_id, body.config, now_str
        )

    # ── Persist ──────────────────────────────────────────────────────────────
    try:
        fq.insert_framework(
            client=bq,
            framework_id=framework_id,
            name=body.name,
            description=body.description,
            base_experiment_id=body.base_experiment_id,
            config_snapshot=config_snapshot,
        )
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error inserting framework: %s",
            request_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    logger.info("[%s] Created framework %s ('%s')", request_id, framework_id, body.name)
    return Framework(
        framework_id=framework_id,
        name=body.name,
        description=body.description,
        created_at=now_str,
        updated_at=now_str,
        base_experiment_id=body.base_experiment_id,
        config=ExperimentConfig.model_validate(config_snapshot),
    )


# ── GET /api/v1/frameworks ───────────────────────────────────────────────────


@router.get(
    "",
    response_model=FrameworkListResponse,
    responses={502: {"model": ErrorResponse}},
    summary="List saved frameworks",
)
def list_frameworks(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    limit: Annotated[
        int, Query(ge=1, le=settings.experiments_max_limit)
    ] = settings.experiments_default_limit,
    cursor: Annotated[str | None, Query()] = None,
) -> FrameworkListResponse:
    offset = decode_cursor(cursor)
    try:
        rows, has_more = fq.list_frameworks(client=bq, limit=limit, offset=offset)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error listing frameworks: %s", request_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    next_cursor = encode_cursor(offset + limit) if has_more else None
    frameworks = [Framework.model_validate(r) for r in rows]
    return FrameworkListResponse(
        data=frameworks,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


# ── GET /api/v1/frameworks/{framework_id} ────────────────────────────────────


@router.get(
    "/{framework_id}",
    response_model=Framework,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Single framework with full config",
)
def get_framework(
    framework_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> Framework:
    try:
        row = fq.get_framework_by_id(bq, framework_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching framework %s: %s",
            request_id, framework_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Framework '{framework_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    return Framework.model_validate(row)


# ── PUT /api/v1/frameworks/{framework_id} ────────────────────────────────────


@router.put(
    "/{framework_id}",
    response_model=Framework,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Update a framework's metadata and/or config",
)
def update_framework(
    framework_id: str,
    body: FrameworkUpdateRequest,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> Framework:
    # Verify framework exists before attempting the update.
    try:
        existing = fq.get_framework_by_id(bq, framework_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching framework %s for update: %s",
            request_id, framework_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Framework '{framework_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    # Build updated config snapshot if a new config was provided.
    new_config_snapshot: dict | None = None
    if body.config is not None:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_config_snapshot = _build_config_snapshot_from_create(
            framework_id, body.config, now_str
        )

    try:
        fq.update_framework(
            client=bq,
            framework_id=framework_id,
            name=body.name,
            description=body.description,
            config_snapshot=new_config_snapshot,
        )
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error updating framework %s: %s",
            request_id, framework_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    # Re-fetch to return the consistent post-update state.
    try:
        updated = fq.get_framework_by_id(bq, framework_id)
    except Exception as exc:
        logger.warning(
            "[%s] Could not re-fetch framework %s after update: %s",
            request_id, framework_id, exc,
        )
        updated = None

    if updated is None:
        # DML completed but streaming buffer hasn't flushed yet — build response
        # from known state rather than failing.
        merged_config = new_config_snapshot or existing["config"]
        return Framework(
            framework_id=framework_id,
            name=body.name if body.name is not None else existing["name"],
            description=body.description if body.description is not None else existing["description"],
            created_at=existing["created_at"],
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            base_experiment_id=existing.get("base_experiment_id"),
            config=ExperimentConfig.model_validate(merged_config),
        )

    return Framework.model_validate(updated)


# ── DELETE /api/v1/frameworks/{framework_id} ─────────────────────────────────


@router.delete(
    "/{framework_id}",
    status_code=204,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Delete a framework",
)
def delete_framework(
    framework_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> Response:
    # Verify exists before deleting (so we can return a meaningful 404).
    try:
        existing = fq.get_framework_by_id(bq, framework_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching framework %s for delete: %s",
            request_id, framework_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Framework '{framework_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    try:
        fq.delete_framework(bq, framework_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error deleting framework %s: %s",
            request_id, framework_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    logger.info("[%s] Deleted framework %s", request_id, framework_id)
    return Response(status_code=204)

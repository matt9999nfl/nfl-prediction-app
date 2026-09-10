"""
Production predictions router.

GET /api/v1/predictions?season=N&week=N

Returns per-game predictions for the current (or specified) week from the most
recent experiment that has cleared its success gate (gate_passed = true).

Tables:
  experiments.backtest_runs     — run metadata + gate status
  platform.experiment_configs   — experiment metadata + gate status
  experiments.backtest_predictions — predictions (season/week partitioned)
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status as http_status
from google.cloud import bigquery

from app.dependencies import get_bq_client, get_request_id, require_api_key
from app.queries import predictions as pq
from app.schemas.common import ErrorResponse
from app.schemas.experiments import (
    PredictionRefreshResponse,
    ProductionPredictionItem,
    ProductionPredictionsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


# ── GET /api/v1/predictions ──────────────────────────────────────────────────


@router.get(
    "",
    response_model=ProductionPredictionsResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Production predictions for a season/week",
    description=(
        "Returns per-game predictions for the specified season and week "
        "from the most recent gate-passed experiment. "
        "Optionally override the experiment via the experiment_id query param."
    ),
)
def get_predictions(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    season: Annotated[int, Query(description="Season year (e.g. 2024) — required")],
    week: Annotated[int, Query(description="Week number (1-18 regular, 19-22 playoffs) — required")],
    experiment_id: Annotated[
        str | None,
        Query(description="Optional override — use this specific experiment instead of auto-selecting"),
    ] = None,
) -> ProductionPredictionsResponse:
    """
    Fetch production predictions for the specified season/week.

    Query params:
      - season (int, required): Season year (e.g. 2024)
      - week (int, required): Week number
      - experiment_id (str, optional): Override — use this specific experiment if provided

    Returns 404 if no gate-passed experiment exists (and no override was provided,
    or the override was not gate-passed).
    """
    try:
        # Step 1: Find the production experiment
        prod_exp = pq.get_production_experiment(bq, experiment_id_override=experiment_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching production experiment: %s",
            request_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if prod_exp is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "No production experiment available",
                "code": "no_production_experiment",
                "request_id": request_id,
            },
        )

    experiment_id_value = prod_exp["experiment_id"]
    experiment_name = prod_exp["experiment_name"]
    completed_at = prod_exp["completed_at"]

    try:
        # Step 2: Fetch predictions for that experiment/season/week
        prediction_rows = pq.get_production_predictions(bq, experiment_id_value, season, week)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching predictions for %s season %s week %s: %s",
            request_id, experiment_id_value, season, week, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    # Build response
    predictions = [ProductionPredictionItem.model_validate(r) for r in prediction_rows]
    return ProductionPredictionsResponse(
        experiment_id=experiment_id_value,
        experiment_name=experiment_name,
        season=season,
        week=week,
        generated_at=completed_at,
        gate_passed=bool(prod_exp.get("gate_passed", False)),
        data=predictions,
    )


# ── POST /api/v1/predictions/refresh ─────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=PredictionRefreshResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Generate predictions for a week",
    description=(
        "Starts the production refresh job, which grades any finished week and "
        "then predicts the next unplayed week. Pass `week` to pin it to a "
        "specific week instead. Returns 202 immediately — the job takes about "
        "two minutes; poll GET /api/v1/predictions to see the result."
    ),
)
def refresh_predictions(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    _: Annotated[None, Depends(require_api_key)],
    season: Annotated[int, Body(embed=True, description="Season year, e.g. 2026")],
    week: Annotated[
        int | None,
        Body(embed=True, description="Optional — pin to this week instead of the next unplayed one"),
    ] = None,
) -> PredictionRefreshResponse:
    """
    Write path, so it sits behind require_api_key like every other trigger here.

    Deliberately does NOT wait for the job. Generating a week loads ~480k plays
    and fits a model; holding an HTTP request open for that would hit Cloud
    Run's 60-second request timeout and report a failure for a job that is
    running fine.
    """
    try:
        execution = pq.trigger_prediction_refresh(season, week)
    except Exception as exc:
        logger.error(
            "[%s] Failed to trigger prediction refresh for %s week %s: %s",
            request_id, season, week, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Could not start the prediction refresh job",
                "code": "job_trigger_failed",
                "request_id": request_id,
            },
        )

    target = f"{season} week {week}" if week is not None else f"{season}, next unplayed week"
    logger.info("[%s] Started prediction refresh for %s → %s", request_id, target, execution)
    return PredictionRefreshResponse(
        status="accepted",
        season=season,
        week=week,
        execution=execution,
        message=(
            f"Generating predictions for {target}. This takes about two minutes; "
            "the picks appear on the dashboard when it finishes."
        ),
    )

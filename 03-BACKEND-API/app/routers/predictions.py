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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from google.cloud import bigquery

from app.dependencies import get_bq_client, get_request_id
from app.queries import predictions as pq
from app.schemas.common import ErrorResponse
from app.schemas.experiments import ProductionPredictionItem, ProductionPredictionsResponse

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
                "error": "No gate-passed experiment found",
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
        data=predictions,
    )

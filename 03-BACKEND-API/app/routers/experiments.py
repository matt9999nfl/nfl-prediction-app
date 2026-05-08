"""
Experiment endpoints — Steps 1 and 3.

Step 1 (read):
  GET  /api/v1/experiments
  GET  /api/v1/experiments/{experiment_id}
  GET  /api/v1/experiments/{experiment_id}/predictions

Step 3 (write + trigger):
  POST /api/v1/experiments
  POST /api/v1/experiments/{experiment_id}/run
  GET  /api/v1/experiments/{experiment_id}/status

Tables:
  platform.experiment_configs   — config read/write
  experiments.backtest_runs     — run metadata read/write
  experiments.backtest_predictions — predictions read (season-partitioned, REQUIRED filter)

Run trigger (POST /{id}/run):
  Validates config completeness, inserts initial backtest_runs row, updates
  experiment status to 'running', then calls trigger_experiment_runner_stub().
  The stub logs the intent; Phase 3 swaps it for a real Cloud Run Job call
  with no router changes.
"""
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from google.cloud import bigquery

from app.config import settings
from app.dependencies import decode_cursor, encode_cursor, get_bq_client, get_request_id, require_api_key
from app.queries import experiments as eq
from app.schemas.common import ErrorResponse, Pagination
from app.schemas.experiments import (
    BacktestRun,
    ExperimentConfig,
    ExperimentCreateRequest,
    ExperimentCreateResponse,
    ExperimentDetailResponse,
    ExperimentListResponse,
    ExperimentRunResponse,
    ExperimentRunStatus,
    PredictionItem,
    PredictionListResponse,
    RunProgress,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


# ── GET /api/v1/experiments ──────────────────────────────────────────────────


@router.get(
    "",
    response_model=ExperimentListResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="List experiment configs",
)
def list_experiments(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    status: Annotated[
        str | None,
        Query(pattern="^(draft|running|complete|failed)$"),
    ] = None,
    target: Annotated[
        str | None,
        Query(pattern="^(ats_cover|outright_winner|total_over|team_total_yards)$"),
    ] = None,
    gate_passed: Annotated[bool | None, Query()] = None,
    limit: Annotated[
        int, Query(ge=1, le=settings.experiments_max_limit)
    ] = settings.experiments_default_limit,
    cursor: Annotated[str | None, Query()] = None,
) -> ExperimentListResponse:
    offset = decode_cursor(cursor)
    try:
        rows, has_more = eq.list_experiments(
            client=bq,
            status=status,
            target=target,
            gate_passed=gate_passed,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("[%s] BigQuery error listing experiments: %s", request_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    next_cursor = encode_cursor(offset + limit) if has_more else None
    configs = [ExperimentConfig.model_validate(r) for r in rows]
    return ExperimentListResponse(
        data=configs,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


# ── GET /api/v1/experiments/{experiment_id} ──────────────────────────────────


@router.get(
    "/{experiment_id}",
    response_model=ExperimentDetailResponse,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Full experiment config with run history",
)
def get_experiment(
    experiment_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> ExperimentDetailResponse:
    try:
        config_row = eq.get_experiment_by_id(bq, experiment_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching experiment %s: %s",
            request_id, experiment_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if config_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Experiment '{experiment_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    try:
        run_rows = eq.get_runs_for_experiment(bq, experiment_id)
    except Exception as exc:
        logger.warning(
            "[%s] Could not fetch runs for experiment %s: %s",
            request_id, experiment_id, exc,
        )
        run_rows = []

    config = ExperimentConfig.model_validate(config_row)
    runs = [BacktestRun.model_validate(r) for r in run_rows]
    latest = runs[0] if runs else None

    return ExperimentDetailResponse(config=config, latest_run=latest, run_history=runs)


# ── GET /api/v1/experiments/{experiment_id}/predictions ──────────────────────


@router.get(
    "/{experiment_id}/predictions",
    response_model=PredictionListResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Per-game predictions from the latest completed run",
    description=(
        "`season` is required to avoid a full-table scan on "
        "experiments.backtest_predictions (partition filter)."
    ),
)
def get_predictions(
    experiment_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    season: Annotated[int, Query(description="Season year — required for partition pruning")],
    fold: Annotated[int | None, Query(ge=0)] = None,
    ol_mismatch_flag: Annotated[bool | None, Query()] = None,
    limit: Annotated[
        int, Query(ge=1, le=settings.predictions_max_limit)
    ] = settings.predictions_default_limit,
    cursor: Annotated[str | None, Query()] = None,
) -> PredictionListResponse:
    offset = decode_cursor(cursor)

    # Ruling #5: ol_mismatch_flag is Phase-1 specific; check column existence before
    # applying the filter.  Missing column + active filter → 400 / unsupported_filter.
    if ol_mismatch_flag is not None:
        try:
            col_exists = eq.check_prediction_column_exists(bq, "ol_mismatch_flag")
        except Exception as exc:
            logger.warning(
                "[%s] Could not verify ol_mismatch_flag column: %s", request_id, exc
            )
            col_exists = False
        if not col_exists:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Filter 'ol_mismatch_flag' is not available on this experiment's predictions",
                    "code": "unsupported_filter",
                    "request_id": request_id,
                },
            )

    try:
        rows, has_more = eq.list_predictions(
            client=bq,
            experiment_id=experiment_id,
            season=season,
            fold=fold,
            ol_mismatch_flag=ol_mismatch_flag,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching predictions for %s season %s: %s",
            request_id, experiment_id, season, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    next_cursor = encode_cursor(offset + limit) if has_more else None
    predictions = [PredictionItem.model_validate(r) for r in rows]
    return PredictionListResponse(
        data=predictions,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


# ── POST /api/v1/experiments ─────────────────────────────────────────────────


@router.post(
    "",
    response_model=ExperimentCreateResponse,
    status_code=201,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Create a new experiment config (status=draft)",
)
def create_experiment(
    body: ExperimentCreateRequest,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> ExperimentCreateResponse:
    # Validate every feature reference before writing anything.
    features_dicts = [f.model_dump() for f in body.features]
    try:
        validation_errors = eq.validate_experiment_features(bq, features_dicts)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error validating experiment features: %s",
            request_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "; ".join(validation_errors),
                "code": "invalid_features",
                "request_id": request_id,
            },
        )

    experiment_id = str(uuid.uuid4())
    try:
        eq.insert_experiment_config(
            client=bq,
            experiment_id=experiment_id,
            name=body.name,
            target=body.target,
            features=features_dicts,
            evaluation=body.evaluation.model_dump(),
            methodology=body.methodology.model_dump(),
            model=body.model.model_dump(),
        )
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error inserting experiment config: %s",
            request_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    logger.info("[%s] Created experiment %s ('%s')", request_id, experiment_id, body.name)
    return ExperimentCreateResponse(experiment_id=experiment_id, status="draft")


# ── POST /api/v1/experiments/{experiment_id}/run ─────────────────────────────


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentRunResponse,
    status_code=202,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Trigger a backtest run for an experiment",
)
def trigger_run(
    experiment_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> ExperimentRunResponse:
    # Fetch config to validate state and extract model/feature metadata.
    try:
        config_row = eq.get_experiment_by_id(bq, experiment_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching experiment %s: %s",
            request_id, experiment_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if config_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Experiment '{experiment_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    if config_row["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail={
                "error": f"Experiment '{experiment_id}' is already running",
                "code": "already_running",
                "request_id": request_id,
            },
        )

    if config_row["status"] not in ("draft", "complete", "failed"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Experiment '{experiment_id}' cannot be run from status '{config_row['status']}'",
                "code": "invalid_status",
                "request_id": request_id,
            },
        )

    # Extract model type and feature column names for the run record.
    model_type: str = config_row["model"]["type"] if config_row.get("model") else "unknown"
    feature_columns: list[str] = [
        f["column"] for f in (config_row.get("features") or [])
    ]

    run_id = str(uuid.uuid4())

    try:
        # Write initial run row first so status polling is immediately consistent.
        eq.insert_initial_run(
            client=bq,
            experiment_id=experiment_id,
            run_id=run_id,
            model_type=model_type,
            feature_columns=feature_columns,
        )
        eq.set_experiment_status(bq, experiment_id, "running")
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error initialising run for experiment %s: %s",
            request_id, experiment_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    # Fire the Cloud Run Job.  Non-fatal — the BQ writes are already committed,
    # so the run record exists regardless.  A trigger failure is logged but does
    # not surface as a 502; the caller still gets 202 and can monitor /status.
    try:
        eq.trigger_experiment_runner(experiment_id, run_id)
        logger.info(
            "[%s] Triggered run %s for experiment %s", request_id, run_id, experiment_id
        )
    except Exception as exc:
        logger.error(
            "[%s] Cloud Run Job trigger failed for experiment %s (run %s): %s",
            request_id, experiment_id, run_id, exc, exc_info=True,
        )

    return ExperimentRunResponse(run_id=run_id, status="running")


# ── GET /api/v1/experiments/{experiment_id}/status ───────────────────────────


@router.get(
    "/{experiment_id}/status",
    response_model=ExperimentRunStatus,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Poll run status for an experiment",
)
def get_run_status(
    experiment_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> ExperimentRunStatus:
    try:
        row = eq.get_experiment_run_status(bq, experiment_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching status for experiment %s: %s",
            request_id, experiment_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Experiment '{experiment_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    # Build optional progress sub-object from runner-populated fields.
    progress: RunProgress | None = None
    folds_complete = row.get("folds_complete")
    folds_total = row.get("folds_total")
    if folds_complete is not None and folds_total is not None:
        progress = RunProgress(folds_complete=folds_complete, folds_total=folds_total)

    return ExperimentRunStatus(
        experiment_id=row["experiment_id"],
        run_id=row.get("run_id"),
        status=row["status"],
        progress=progress,
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        error=row.get("error_message"),
    )


# ── POST /api/v1/experiments/{experiment_id}/cancel ──────────────────────────


@router.post(
    "/{experiment_id}/cancel",
    response_model=ExperimentCreateResponse,
    status_code=200,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Cancel a running experiment and reset it to failed",
)
def cancel_experiment(
    experiment_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    _: Annotated[None, Depends(require_api_key)],
) -> ExperimentCreateResponse:
    try:
        config_row = eq.get_experiment_by_id(bq, experiment_id)
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error fetching experiment %s: %s",
            request_id, experiment_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if config_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Experiment '{experiment_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    if config_row["status"] not in ("running",):
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Experiment '{experiment_id}' is not running (status='{config_row['status']}')",
                "code": "invalid_status",
                "request_id": request_id,
            },
        )

    try:
        eq.set_experiment_status(bq, experiment_id, "failed")
    except Exception as exc:
        logger.error(
            "[%s] BigQuery error cancelling experiment %s: %s",
            request_id, experiment_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    logger.info("[%s] Cancelled experiment %s", request_id, experiment_id)
    return ExperimentCreateResponse(experiment_id=experiment_id, status="failed")

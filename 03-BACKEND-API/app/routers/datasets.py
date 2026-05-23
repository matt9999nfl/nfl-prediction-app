"""
Dataset endpoints — Steps 2 and 5.

Step 2:
  POST   /api/v1/datasets/upload              — receive file, write to GCS, background task
  GET    /api/v1/datasets                     — list datasets (paginated)
  GET    /api/v1/datasets/{dataset_id}        — single dataset with column metadata
  PUT    /api/v1/datasets/{dataset_id}/schema — confirm schema mapping → status='ready'
  DELETE /api/v1/datasets/{dataset_id}        — delete if not referenced by any experiment

Step 5:
  POST   /api/v1/datasets/{dataset_id}/infer-schema — Claude AI schema inference (read-only)

Upload flow (per spec Step 2):
  1. Validate file type and size (synchronous, before 202).
  2. Generate dataset_id UUID.
  3. Upload raw bytes to GCS: gs://nfl-model-471509-uploads/{dataset_id}/raw.{ext}
  4. Insert initial row into platform.datasets (status='uploading').
  5. Register background task: parse → BQ load → column stats → status='mapping'.
  6. Return 202 immediately with dataset_id and schema_job_id.

The frontend polls GET /datasets/{id} to observe status transitions:
  uploading → mapping → ready (or error)

Infer-schema flow (Step 5):
  1. Verify dataset exists and is in a queryable state (mapping or ready).
  2. Fetch first 5 rows from user_datasets.{id} for sample values.
  3. Fetch existing platform.dataset_columns rows for null_rate lookup.
  4. Call Claude API with column names + sample rows.
  5. Return suggestions for user review — does NOT write to any tables.
  503 if Claude API is unavailable; frontend falls back to the manual form.
"""
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from google.cloud import bigquery

from app.claude_inference import ClaudeInferenceError, infer_dataset_schema
from app.config import settings
from app.dependencies import decode_cursor, encode_cursor, get_bq_client, get_request_id
from app.queries import datasets as dq
from app.schemas.common import ErrorResponse, Pagination
from app.schemas.datasets import (
    Dataset,
    DatasetColumn,
    DatasetDeleteResponse,
    DatasetDetail,
    DatasetListResponse,
    DatasetUploadResponse,
    DataQualityFlag,
    InferSchemaResponse,
    SchemaUpdateRequest,
)
from app.storage import get_storage_client, upload_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])

_ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "json"}
_MAX_FILE_BYTES = 50 * 1024 * 1024   # 50 MB


def _ext(filename: str | None) -> str | None:
    """Extract lower-case extension (without dot) from a filename."""
    if not filename:
        return None
    suffix = Path(filename).suffix.lstrip(".").lower()
    return suffix if suffix else None


# ── POST /api/v1/datasets/upload ─────────────────────────────────────────────


@router.post(
    "/upload",
    status_code=202,
    response_model=DatasetUploadResponse,
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Upload a new dataset file",
    description=(
        "Accepts CSV, Excel (.xlsx/.xls), or JSON (array of objects).  "
        "Max 50 MB.  Returns 202 immediately; processing happens async.  "
        "Poll GET /datasets/{dataset_id} to observe status transitions: "
        "uploading → mapping → ready (or error)."
    ),
)
async def upload_dataset(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    file: Annotated[UploadFile, File(description="CSV, Excel, or JSON file (max 50 MB)")],
    name: Annotated[str, Form(description="Human-readable dataset name")],
    description: Annotated[str, Form(description="What this dataset contains")],
    license_tag: Annotated[
        str,
        Form(description='"open" | "licensed_commercial" | "personal_use_only"'),
    ],
) -> DatasetUploadResponse:
    # ── Validate file extension ───────────────────────────────────────────────
    ext = _ext(file.filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Unsupported file type '{ext or 'unknown'}'.  "
                    f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
                ),
                "code": "invalid_params",
                "request_id": request_id,
            },
        )

    # ── Validate license_tag ──────────────────────────────────────────────────
    valid_tags = {"open", "licensed_commercial", "personal_use_only"}
    if license_tag not in valid_tags:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid license_tag '{license_tag}'. Allowed: {', '.join(sorted(valid_tags))}",
                "code": "invalid_params",
                "request_id": request_id,
            },
        )

    # ── Read and size-check file content ──────────────────────────────────────
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"File too large ({len(content) // (1024*1024)} MB).  Maximum is 50 MB.",
                "code": "invalid_params",
                "request_id": request_id,
            },
        )

    dataset_id = str(uuid.uuid4())
    schema_job_id = str(uuid.uuid4())

    # ── Upload raw file to GCS (synchronous, per spec) ────────────────────────
    try:
        gcs = get_storage_client()
        upload_file(gcs, dataset_id, content, ext)
    except Exception as exc:
        logger.error("[%s] GCS upload failed for dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Could not write file to Cloud Storage",
                "code": "upstream_error",
                "request_id": request_id,
            },
        )

    # ── Insert initial metadata row (synchronous, per spec) ───────────────────
    from datetime import datetime, timezone
    try:
        dq.insert_dataset_row(
            bq,
            dataset_id=dataset_id,
            name=name,
            description=description,
            license_tag=license_tag,
            upload_date=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.error("[%s] BQ metadata insert failed for dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Could not register dataset in BigQuery",
                "code": "upstream_error",
                "request_id": request_id,
            },
        )

    # ── Trigger the Cloud Run Job for async processing ────────────────────────
    # Non-fatal: the GCS file and metadata row are already committed.
    # A trigger failure is logged; the dataset status stays 'uploading' and
    # the operator can re-trigger the job manually via gcloud.
    try:
        dq.trigger_dataset_processor(dataset_id, ext)
    except Exception as exc:
        logger.error(
            "[%s] Cloud Run Job trigger failed for dataset %s: %s",
            request_id, dataset_id, exc, exc_info=True,
        )

    logger.info("[%s] Dataset %s accepted, Cloud Run Job triggered", request_id, dataset_id)
    return DatasetUploadResponse(dataset_id=dataset_id, schema_job_id=schema_job_id)


# ── GET /api/v1/datasets ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=DatasetListResponse,
    responses={502: {"model": ErrorResponse}},
    summary="List all registered datasets",
)
def list_datasets(
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
    status: Annotated[
        str | None,
        Query(pattern="^(uploading|mapping|ready|error)$"),
    ] = None,
    license_tag: Annotated[
        str | None,
        Query(pattern="^(open|licensed_commercial|personal_use_only)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> DatasetListResponse:
    offset = decode_cursor(cursor)
    try:
        rows, has_more = dq.list_datasets(bq, status, license_tag, limit, offset)
    except Exception as exc:
        logger.error("[%s] BQ error listing datasets: %s", request_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    next_cursor = encode_cursor(offset + limit) if has_more else None
    return DatasetListResponse(
        data=[Dataset.model_validate(r) for r in rows],
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
    )


# ── GET /api/v1/datasets/{dataset_id} ────────────────────────────────────────


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetail,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Single dataset with full column metadata",
)
def get_dataset(
    dataset_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> DatasetDetail:
    try:
        row = dq.get_dataset(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] BQ error fetching dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Dataset '{dataset_id}' not found",
                "code": "not_found",
                "request_id": request_id,
            },
        )

    # Column metadata is best-effort: return empty list if the columns table
    # hasn't been populated yet (background task still running).
    columns: list[DatasetColumn] = []
    try:
        col_rows = dq.get_dataset_columns(bq, dataset_id)
        columns = [DatasetColumn.model_validate(c) for c in col_rows]
    except Exception as exc:
        logger.warning("[%s] Could not fetch columns for dataset %s: %s", request_id, dataset_id, exc)

    return DatasetDetail(**row, columns=columns)


# ── PUT /api/v1/datasets/{dataset_id}/schema ─────────────────────────────────


@router.put(
    "/{dataset_id}/schema",
    response_model=Dataset,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Submit or update column schema mapping",
    description=(
        "Confirms schema mapping (form-based or AI-suggested).  "
        "Sets status to 'ready' and marks join-key columns.  "
        "Response is the updated Dataset object."
    ),
)
def update_schema(
    dataset_id: str,
    body: SchemaUpdateRequest,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> Dataset:
    # Verify the dataset exists.
    try:
        row = dq.get_dataset(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] BQ error verifying dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Dataset '{dataset_id}' not found", "code": "not_found", "request_id": request_id},
        )

    # Validate join_key_columns structure.
    expected_keys: dict[str, set[str]] = {
        "game_id":            {"game_id"},
        "player_season_week": {"player_id", "season", "week"},
        "team_season_week":   {"team", "season", "week"},
    }
    required = expected_keys.get(body.join_key_type, set())
    provided = set(body.join_key_columns.keys())
    if provided != required:
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"join_key_columns for '{body.join_key_type}' must have keys "
                    f"{sorted(required)}, got {sorted(provided)}"
                ),
                "code": "invalid_params",
                "request_id": request_id,
            },
        )

    # Fetch existing column rows once — used for both validation and null_rate carry-over.
    try:
        existing_col_rows = dq.get_dataset_columns(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] BQ error fetching columns for %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    existing_cols = {c["column_name"] for c in existing_col_rows}
    null_rate_map = {c["column_name"]: c.get("null_rate", 0.0) for c in existing_col_rows}

    # Validate that all column_names in the request exist in this dataset.
    unknown_cols = {c.column_name for c in body.columns} - existing_cols
    if unknown_cols:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Unknown column names in schema update: {sorted(unknown_cols)}",
                "code": "invalid_params",
                "request_id": request_id,
            },
        )

    # Validate that join_key_columns values reference existing columns.
    unknown_jk = set(body.join_key_columns.values()) - existing_cols
    if unknown_jk:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"join_key_columns reference unknown columns: {sorted(unknown_jk)}",
                "code": "invalid_params",
                "request_id": request_id,
            },
        )

    # Determine which column names are join keys.
    join_key_column_names = set(body.join_key_columns.values())

    column_updates = [
        {
            "column_name":   c.column_name,
            "semantic_name": c.semantic_name,
            "description":   c.description,
            "data_type":     c.data_type,
            "null_rate":     null_rate_map.get(c.column_name, 0.0),
        }
        for c in body.columns
    ]

    # Apply updates.
    try:
        dq.replace_dataset_columns(bq, dataset_id, join_key_column_names, column_updates)
        dq.update_dataset_schema_metadata(
            bq, dataset_id, body.join_key_type, body.join_key_columns, body.schema_source
        )
    except Exception as exc:
        logger.error("[%s] BQ schema update failed for %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Schema update failed", "code": "upstream_error", "request_id": request_id},
        )

    # Return the updated dataset row.
    try:
        updated = dq.get_dataset(bq, dataset_id)
    except Exception:
        updated = None

    if updated is None:
        raise HTTPException(
            status_code=502,
            detail={"error": "Could not read updated dataset", "code": "upstream_error", "request_id": request_id},
        )

    return Dataset.model_validate(updated)


# ── DELETE /api/v1/datasets/{dataset_id} ─────────────────────────────────────


@router.delete(
    "/{dataset_id}",
    status_code=200,
    response_model=DatasetDeleteResponse,
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Delete a dataset",
    description=(
        "Removes the dataset registry entry (platform.datasets + dataset_columns) "
        "and attempts to delete the raw upload file from GCS.  "
        "GCS delete failures are logged but do not fail the response.  "
        "Returns 200 on success; 404 if the dataset does not exist."
    ),
)
def delete_dataset(
    dataset_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> DatasetDeleteResponse:
    # Verify it exists.
    try:
        row = dq.get_dataset(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] BQ error verifying dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Dataset '{dataset_id}' not found", "code": "not_found", "request_id": request_id},
        )

    # Delete registry rows from platform.datasets and platform.dataset_columns.
    # Does NOT drop the user_datasets BigQuery table (scope excluded per P5-03 spec).
    try:
        dq.delete_dataset_registry_only(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] Registry delete failed for dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Delete operation failed", "code": "upstream_error", "request_id": request_id},
        )

    # Attempt GCS file delete — non-fatal.
    dq.delete_dataset_gcs_file(dataset_id)

    logger.info("[%s] Dataset %s deleted (registry only)", request_id, dataset_id)
    return DatasetDeleteResponse(
        message="Dataset deleted successfully",
        dataset_id=dataset_id,
    )


# ── POST /api/v1/datasets/{dataset_id}/infer-schema ──────────────────────────


# Statuses that mean data is available in user_datasets.{id} for sampling.
_INFERRABLE_STATUSES = frozenset({"mapping", "ready"})


@router.post(
    "/{dataset_id}/infer-schema",
    response_model=InferSchemaResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"description": "Claude API unavailable — frontend should fall back to manual form"},
    },
    summary="AI-assisted schema inference via Claude API",
    description=(
        "Calls Claude with column names and sample rows from the dataset.  "
        "Returns suggested mappings for user review — does NOT apply them.  "
        "Confirm via PUT /schema with schema_source='ai_assisted'.  "
        "Returns 503 with fallback='use_form' if Claude is unavailable."
    ),
)
def infer_schema(
    dataset_id: str,
    request: Request,
    request_id: Annotated[str, Depends(get_request_id)],
    bq: Annotated[bigquery.Client, Depends(get_bq_client)],
) -> InferSchemaResponse | JSONResponse:
    # ── 1. Verify dataset exists and data is ready for sampling ───────────────
    try:
        ds_row = dq.get_dataset(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] BQ error fetching dataset %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    if ds_row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Dataset '{dataset_id}' not found", "code": "not_found", "request_id": request_id},
        )

    if ds_row["status"] not in _INFERRABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": (
                    f"Dataset '{dataset_id}' is not ready for inference "
                    f"(status='{ds_row['status']}').  "
                    "Wait for the upload to complete (status='mapping') before calling infer-schema."
                ),
                "code": "dataset_not_ready",
                "request_id": request_id,
            },
        )

    # ── 2. Fetch existing column metadata for null_rate lookup ────────────────
    try:
        existing_col_rows = dq.get_dataset_columns(bq, dataset_id)
    except Exception as exc:
        logger.error("[%s] BQ error fetching columns for %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    null_rate_map: dict[str, float] = {c["column_name"]: c.get("null_rate", 0.0) for c in existing_col_rows}
    data_type_map: dict[str, str] = {c["column_name"]: c.get("data_type", "categorical") for c in existing_col_rows}

    # ── 3. Fetch sample rows from user_datasets.{id} ─────────────────────────
    try:
        sample_rows = dq.get_dataset_sample_rows(bq, dataset_id, limit=5)
    except Exception as exc:
        logger.error("[%s] BQ error fetching sample rows for %s: %s", request_id, dataset_id, exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "Upstream query failed", "code": "upstream_error", "request_id": request_id},
        )

    column_names = list(null_rate_map.keys()) or (
        list(sample_rows[0].keys()) if sample_rows else []
    )

    # ── 4. Call Claude ────────────────────────────────────────────────────────
    if not settings.anthropic_api_key:
        logger.warning("[%s] ANTHROPIC_API_KEY not set — returning ai_unavailable", request_id)
        return JSONResponse(
            status_code=503,
            content={"error": "ai_unavailable", "fallback": "use_form"},
        )

    try:
        raw = infer_dataset_schema(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            column_names=column_names,
            sample_rows=sample_rows,
        )
    except ClaudeInferenceError as exc:
        logger.warning("[%s] Claude inference failed for dataset %s: %s", request_id, dataset_id, exc)
        return JSONResponse(
            status_code=503,
            content={"error": "ai_unavailable", "fallback": "use_form"},
        )

    # ── 5. Build response: merge Claude output with dataset context ───────────
    suggested_join_key_columns: dict[str, str] = raw.get("suggested_join_key_columns") or {}
    join_key_col_values = set(suggested_join_key_columns.values())

    # Coerce data_type to a valid literal; fall back to existing stats then "categorical".
    _VALID_DATA_TYPES = {"numeric", "categorical", "boolean"}

    suggested_columns: list[DatasetColumn] = []
    for col_suggestion in (raw.get("suggested_columns") or []):
        col_name = col_suggestion.get("column_name", "")
        raw_dtype = col_suggestion.get("data_type", "")
        coerced_dtype = raw_dtype if raw_dtype in _VALID_DATA_TYPES else data_type_map.get(col_name, "categorical")
        suggested_columns.append(
            DatasetColumn(
                dataset_id=dataset_id,
                column_name=col_name,
                semantic_name=col_suggestion.get("semantic_name") or None,
                description=col_suggestion.get("description") or None,
                data_type=coerced_dtype,
                is_join_key=col_name in join_key_col_values,
                null_rate=null_rate_map.get(col_name, 0.0),
            )
        )

    data_quality_flags: list[DataQualityFlag] = []
    for flag in (raw.get("data_quality_flags") or []):
        sev = flag.get("severity", "warning")
        if sev not in ("warning", "error"):
            sev = "warning"
        data_quality_flags.append(
            DataQualityFlag(
                column=flag.get("column", ""),
                issue=flag.get("issue", ""),
                severity=sev,
            )
        )

    # Clamp confidence to [0, 1].
    confidence = float(raw.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    logger.info(
        "[%s] Schema inference complete for dataset %s — confidence=%.2f cols=%d flags=%d",
        request_id, dataset_id, confidence, len(suggested_columns), len(data_quality_flags),
    )

    return InferSchemaResponse(
        suggested_join_key_type=raw["suggested_join_key_type"],
        suggested_join_key_columns=suggested_join_key_columns,
        suggested_columns=suggested_columns,
        data_quality_flags=data_quality_flags,
        confidence=confidence,
    )

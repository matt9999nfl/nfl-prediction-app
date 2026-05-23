"""
Dataset schemas.  Matches API_CONTRACTS.md → Dataset, DatasetColumn types exactly.

upload_date: ISO 8601 string (not a datetime object) to match the contract convention.
schema_source: defaults to "form" at upload time; "ai_assisted" when the user confirms
               a Claude-suggested mapping via PUT /schema with schema_source="ai_assisted".

Step 5 additions:
  DataQualityFlag  — one per issue Claude surfaces (e.g. high null rate, ambiguous type)
  InferSchemaResponse — 200 body for POST /datasets/{id}/infer-schema.
                        suggested_columns uses the full DatasetColumn type; is_join_key
                        is derived from suggested_join_key_columns, and null_rate is
                        carried from the existing platform.dataset_columns stats.
"""
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Pagination


# ── Core types ────────────────────────────────────────────────────────────────

class Dataset(BaseModel):
    dataset_id: str
    name: str
    description: str
    upload_date: str                    # ISO 8601
    join_key_type: Literal[
        "game_id", "player_season_week", "team_season_week"
    ] | None = None                     # null until schema mapping is confirmed
    row_count: int | None = None        # null until async processing completes
    column_count: int | None = None
    license_tag: Literal["open", "licensed_commercial", "personal_use_only"]
    status: Literal["uploading", "mapping", "ready", "error"]
    schema_source: Literal["form", "ai_assisted"]


class DatasetColumn(BaseModel):
    dataset_id: str
    column_name: str                    # raw column name from the uploaded file
    semantic_name: str | None = None    # null until schema mapping is confirmed
    description: str | None = None
    data_type: Literal["numeric", "categorical", "boolean"]
    is_join_key: bool
    null_rate: float                    # 0..1


class DatasetDetail(Dataset):
    """Dataset extended with column metadata (returned by GET /datasets/{id})."""
    columns: list[DatasetColumn] = []


# ── List response ─────────────────────────────────────────────────────────────

class DatasetListResponse(BaseModel):
    data: list[Dataset]
    pagination: Pagination


# ── Upload response ───────────────────────────────────────────────────────────

class DatasetUploadResponse(BaseModel):
    dataset_id: str
    status: str = "uploading"
    schema_job_id: str                  # UUID tracking the background processing job


# ── Delete response ───────────────────────────────────────────────────────────

class DatasetDeleteResponse(BaseModel):
    message: str
    dataset_id: str


# ── Schema update request ─────────────────────────────────────────────────────

class ColumnMapping(BaseModel):
    """Per-column schema mapping submitted by the user."""
    column_name: str
    semantic_name: str
    description: str
    data_type: Literal["numeric", "categorical", "boolean"]


class SchemaUpdateRequest(BaseModel):
    """
    Body for PUT /api/v1/datasets/{dataset_id}/schema.

    join_key_columns format depends on join_key_type:
      game_id            → {"game_id": "column_name_in_file"}
      player_season_week → {"player_id": "...", "season": "...", "week": "..."}
      team_season_week   → {"team": "...", "season": "...", "week": "..."}

    schema_source: defaults to "form".  Step 5 (infer-schema) passes "ai_assisted"
    when the user confirms a Claude-suggested mapping via this endpoint.
    """
    join_key_type: Literal["game_id", "player_season_week", "team_season_week"]
    join_key_columns: dict[str, str]
    columns: list[ColumnMapping]
    schema_source: Literal["form", "ai_assisted"] = "form"


# ── Step 5: infer-schema response ─────────────────────────────────────────────


class DataQualityFlag(BaseModel):
    """A single data quality issue surfaced by Claude during schema inference."""
    column: str
    issue: str
    severity: Literal["warning", "error"]


class InferSchemaResponse(BaseModel):
    """
    200 response for POST /api/v1/datasets/{dataset_id}/infer-schema.

    suggested_columns uses DatasetColumn so the frontend can display and
    pre-populate the schema mapping form.  is_join_key is derived from
    suggested_join_key_columns; null_rate is carried from existing stats.

    This endpoint is read-only — it does not write to platform.datasets or
    platform.dataset_columns.  The user confirms via PUT /schema, passing
    schema_source="ai_assisted".
    """
    suggested_join_key_type: Literal["game_id", "player_season_week", "team_season_week"]
    suggested_join_key_columns: dict[str, str]   # role → column_name_in_file
    suggested_columns: list[DatasetColumn]
    data_quality_flags: list[DataQualityFlag]
    confidence: float

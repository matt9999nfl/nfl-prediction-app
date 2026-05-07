"""
BigQuery queries for the /frameworks endpoints.

Table: platform.frameworks

Schema (inferred from API_CONTRACTS.md Framework type):
  framework_id       STRING  NOT NULL
  name               STRING  NOT NULL
  description        STRING  NOT NULL
  created_at         TIMESTAMP NOT NULL
  updated_at         TIMESTAMP NOT NULL
  base_experiment_id STRING   NULLABLE
  config_snapshot    STRING   NOT NULL  -- JSON blob of ExperimentConfig

All writes use:
  - Streaming insert (insert_rows_json) for INSERT — fast, low latency.
  - Blocking DML for UPDATE / DELETE — immediately visible to subsequent reads.

JSON parsing:
  config_snapshot is stored as a JSON string and parsed back to a dict on read.
  _normalize_framework() handles this transparently.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


def _run_dml(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> None:
    """Execute a DML statement and block until complete."""
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    client.query(query, job_config=job_config).result()


def _streaming_insert(
    client: bigquery.Client,
    table_ref: str,
    rows: list[dict[str, Any]],
) -> None:
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise ValueError(f"BigQuery streaming insert errors: {errors}")


def _normalize_framework(row: dict[str, Any]) -> dict[str, Any]:
    """Parse config_snapshot JSON and normalise timestamps in a framework row."""
    row = dict(row)
    config = row.get("config_snapshot")
    if isinstance(config, str):
        try:
            row["config_snapshot"] = json.loads(config)
        except json.JSONDecodeError:
            pass  # leave as-is; will fail downstream schema validation
    # Ensure timestamps are strings
    for field in ("created_at", "updated_at"):
        val = row.get(field)
        if val is not None and not isinstance(val, str):
            row[field] = val.isoformat()
    return row


def _framework_select() -> str:
    """Column projection for platform.frameworks → Framework schema."""
    return """
        framework_id,
        name,
        description,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', created_at) AS created_at,
        FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', updated_at) AS updated_at,
        base_experiment_id,
        config_snapshot
    """


def _row_to_framework_dict(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a normalised DB row to a dict matching the Framework schema.
    Renames config_snapshot → config for Pydantic model_validate().
    """
    row = _normalize_framework(row)
    config = row.pop("config_snapshot", None)
    row["config"] = config
    return row


# ── Read ──────────────────────────────────────────────────────────────────────


def list_frameworks(
    client: bigquery.Client,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return a paginated list of frameworks, newest first."""
    params = [
        bigquery.ScalarQueryParameter("lim", "INT64", limit + 1),
        bigquery.ScalarQueryParameter("off", "INT64", offset),
    ]
    query = f"""
        SELECT {_framework_select()}
        FROM `{PROJECT}.platform.frameworks`
        ORDER BY created_at DESC
        LIMIT @lim OFFSET @off
    """
    rows = _run_query(client, query, params)
    has_more = len(rows) > limit
    return [_row_to_framework_dict(r) for r in rows[:limit]], has_more


def get_framework_by_id(
    client: bigquery.Client,
    framework_id: str,
) -> dict[str, Any] | None:
    """Return a single framework row, or None if not found."""
    query = f"""
        SELECT {_framework_select()}
        FROM `{PROJECT}.platform.frameworks`
        WHERE framework_id = @framework_id
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("framework_id", "STRING", framework_id)]
    rows = _run_query(client, query, params)
    return _row_to_framework_dict(rows[0]) if rows else None


# ── Write ─────────────────────────────────────────────────────────────────────


def insert_framework(
    client: bigquery.Client,
    framework_id: str,
    name: str,
    description: str,
    base_experiment_id: str | None,
    config_snapshot: dict[str, Any],
) -> None:
    """Insert a new framework row (streaming insert)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _streaming_insert(
        client,
        f"{PROJECT}.platform.frameworks",
        [{
            "framework_id":        framework_id,
            "name":                name,
            "description":         description,
            "created_at":          now,
            "updated_at":          now,
            "base_experiment_id":  base_experiment_id,
            "config_snapshot":     json.dumps(config_snapshot),
        }],
    )


def update_framework(
    client: bigquery.Client,
    framework_id: str,
    name: str | None,
    description: str | None,
    config_snapshot: dict[str, Any] | None,
) -> None:
    """
    DML UPDATE — only touches the columns that are provided (non-None).
    Always updates updated_at.
    """
    set_clauses: list[str] = ["updated_at = CURRENT_TIMESTAMP()"]
    params: list[bigquery.ScalarQueryParameter] = []

    if name is not None:
        set_clauses.append("name = @name")
        params.append(bigquery.ScalarQueryParameter("name", "STRING", name))

    if description is not None:
        set_clauses.append("description = @description")
        params.append(bigquery.ScalarQueryParameter("description", "STRING", description))

    if config_snapshot is not None:
        set_clauses.append("config_snapshot = @config_snapshot")
        params.append(
            bigquery.ScalarQueryParameter(
                "config_snapshot", "STRING", json.dumps(config_snapshot)
            )
        )

    params.append(bigquery.ScalarQueryParameter("framework_id", "STRING", framework_id))

    _run_dml(
        client,
        f"""
        UPDATE `{PROJECT}.platform.frameworks`
        SET    {', '.join(set_clauses)}
        WHERE  framework_id = @framework_id
        """,
        params,
    )


def delete_framework(
    client: bigquery.Client,
    framework_id: str,
) -> None:
    """DML DELETE — synchronous, immediately visible to subsequent reads."""
    _run_dml(
        client,
        f"DELETE FROM `{PROJECT}.platform.frameworks` WHERE framework_id = @framework_id",
        [bigquery.ScalarQueryParameter("framework_id", "STRING", framework_id)],
    )

"""
BigQuery and file-processing operations for the /datasets endpoints.

Write strategy:
  - Initial metadata INSERT:  streaming insert (insert_rows_json) — fast, low latency.
  - Status UPDATEs (DML):     blocking DML — immediately visible to subsequent reads.
  - Column rows INSERT:       streaming insert — fast for potentially many rows.
  - Column rows DELETE+replace: DML DELETE followed by streaming INSERT.
  - BigQuery table for user data: load_table_from_dataframe (creates table if absent).

Note: BigQuery streaming inserts have a short buffer delay (~seconds) before rows
are visible in SELECT queries.  For a single-user tool this is acceptable — the
202 response is returned first and the frontend polls the status endpoint.
"""
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project


# ── Low-level helpers ─────────────────────────────────────────────────────────


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


def _to_bq_table_name(dataset_id: str) -> str:
    """
    Sanitize a UUID dataset_id for use as a BigQuery table name.
    BigQuery table names must match [A-Za-z0-9_]; UUIDs contain hyphens.
    """
    return dataset_id.replace("-", "_")


# ── Read: platform.datasets ───────────────────────────────────────────────────


_UPLOAD_TIMEOUT_MINUTES = 30
_UPLOAD_TIMEOUT_MESSAGE = (
    "Processing job did not complete within 30 minutes. "
    "The upload may have failed. Please delete this entry and try again."
)


def _reconcile_stuck_uploading(
    client: bigquery.Client,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Lazy reconciliation: for any row with status='uploading' and upload_date
    more than 30 minutes ago, flip it to status='error' in BigQuery and update
    the in-memory row so the response reflects the corrected state.

    Called after a list or single-row query returns results.
    """
    from datetime import datetime, timezone, timedelta

    timeout_cutoff = datetime.now(timezone.utc) - timedelta(minutes=_UPLOAD_TIMEOUT_MINUTES)

    reconciled: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "uploading":
            reconciled.append(row)
            continue

        # Parse upload_date (stored as ISO 8601 string from FORMAT_TIMESTAMP).
        upload_date_str: str | None = row.get("upload_date")
        if not upload_date_str:
            reconciled.append(row)
            continue

        try:
            upload_dt = datetime.fromisoformat(upload_date_str.replace("Z", "+00:00"))
        except ValueError:
            reconciled.append(row)
            continue

        if upload_dt > timeout_cutoff:
            # Not yet timed out — leave as-is.
            reconciled.append(row)
            continue

        # Timed out — flip to error in BigQuery.
        dataset_id = row["dataset_id"]
        try:
            _run_dml(
                client,
                f"""
                UPDATE `{PROJECT}.platform.datasets`
                SET   status        = 'error',
                      updated_at    = CURRENT_TIMESTAMP()
                WHERE dataset_id    = @dataset_id
                  AND status        = 'uploading'
                """,
                [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
            )
            logger.info(
                "Reconciled stuck uploading dataset %s to error (upload_date=%s)",
                dataset_id, upload_date_str,
            )
        except Exception as exc:
            logger.warning(
                "Could not reconcile stuck dataset %s: %s", dataset_id, exc
            )

        # Return the corrected row regardless of whether the DML succeeded —
        # if DML failed, showing error state is still the right UX.
        updated_row = dict(row)
        updated_row["status"] = "error"
        reconciled.append(updated_row)

    return reconciled


def list_datasets(
    client: bigquery.Client,
    status: str | None,
    license_tag: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], bool]:
    conditions: list[str] = []
    params: list[bigquery.ScalarQueryParameter] = []

    if status is not None:
        conditions.append("status = @status")
        params.append(bigquery.ScalarQueryParameter("status", "STRING", status))

    if license_tag is not None:
        conditions.append("license_tag = @license_tag")
        params.append(bigquery.ScalarQueryParameter("license_tag", "STRING", license_tag))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    params.extend([
        bigquery.ScalarQueryParameter("lim", "INT64", limit + 1),
        bigquery.ScalarQueryParameter("off", "INT64", offset),
    ])

    query = f"""
        SELECT
            dataset_id,
            name,
            description,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', upload_date) AS upload_date,
            join_key_type,
            row_count,
            column_count,
            license_tag,
            status,
            schema_source
        FROM `{PROJECT}.platform.datasets`
        {where}
        ORDER BY upload_date DESC
        LIMIT @lim OFFSET @off
    """

    rows = _run_query(client, query, params)
    has_more = len(rows) > limit
    result = _reconcile_stuck_uploading(client, rows[:limit])
    return result, has_more


def get_dataset(
    client: bigquery.Client,
    dataset_id: str,
) -> dict[str, Any] | None:
    query = f"""
        SELECT
            dataset_id,
            name,
            description,
            FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', upload_date) AS upload_date,
            join_key_type,
            row_count,
            column_count,
            license_tag,
            status,
            schema_source
        FROM `{PROJECT}.platform.datasets`
        WHERE dataset_id = @dataset_id
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)]
    rows = _run_query(client, query, params)
    if not rows:
        return None
    reconciled = _reconcile_stuck_uploading(client, rows)
    return reconciled[0]


def get_dataset_columns(
    client: bigquery.Client,
    dataset_id: str,
) -> list[dict[str, Any]]:
    query = f"""
        SELECT
            dataset_id,
            column_name,
            semantic_name,
            description,
            data_type,
            is_join_key,
            null_rate
        FROM `{PROJECT}.platform.dataset_columns`
        WHERE dataset_id = @dataset_id
        ORDER BY column_name ASC
    """
    params = [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)]
    return _run_query(client, query, params)


def is_dataset_referenced_in_experiments(
    client: bigquery.Client,
    dataset_id: str,
) -> bool:
    """
    Check whether any experiment config references this dataset in its features list.
    Uses a string search on the serialized features JSON — dataset_ids are UUIDs,
    so false positives are astronomically unlikely.
    """
    dataset_ref = f"user_datasets.{dataset_id}"
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT}.platform.experiment_configs`
        WHERE TO_JSON_STRING(features) LIKE CONCAT('%', @dataset_ref, '%')
    """
    params = [bigquery.ScalarQueryParameter("dataset_ref", "STRING", dataset_ref)]
    rows = _run_query(client, query, params)
    return int(rows[0]["cnt"]) > 0 if rows else False


# ── Write: platform.datasets ──────────────────────────────────────────────────


def insert_dataset_row(
    client: bigquery.Client,
    dataset_id: str,
    name: str,
    description: str,
    license_tag: str,
    upload_date: datetime,
) -> None:
    """Insert an initial dataset metadata row with status='uploading'."""
    now_str = upload_date.strftime("%Y-%m-%d %H:%M:%S UTC")
    _streaming_insert(
        client,
        f"{PROJECT}.platform.datasets",
        [{
            "dataset_id":    dataset_id,
            "name":          name,
            "description":   description,
            "upload_date":   now_str,
            "join_key_type": None,
            "row_count":     None,
            "column_count":  None,
            "license_tag":   license_tag,
            "status":        "uploading",
            "schema_source": "form",
            "created_at":    now_str,
            "updated_at":    now_str,
        }],
    )


def update_dataset_after_processing(
    client: bigquery.Client,
    dataset_id: str,
    status: str,
    row_count: int | None,
    column_count: int | None,
) -> None:
    """DML update — called by the background task once file processing completes."""
    _run_dml(
        client,
        f"""
        UPDATE `{PROJECT}.platform.datasets`
        SET   status       = @status,
              row_count    = @row_count,
              column_count = @column_count,
              updated_at   = CURRENT_TIMESTAMP()
        WHERE dataset_id   = @dataset_id
        """,
        [
            bigquery.ScalarQueryParameter("status",       "STRING", status),
            bigquery.ScalarQueryParameter("row_count",    "INT64",  row_count),
            bigquery.ScalarQueryParameter("column_count", "INT64",  column_count),
            bigquery.ScalarQueryParameter("dataset_id",   "STRING", dataset_id),
        ],
    )


def update_dataset_schema_metadata(
    client: bigquery.Client,
    dataset_id: str,
    join_key_type: str,
    join_key_columns: dict[str, str] | None = None,  # not stored — table has no such column
    schema_source: str = "form",
) -> None:
    """DML update — called by PUT /schema to store join key info and flip status to ready."""
    _run_dml(
        client,
        f"""
        UPDATE `{PROJECT}.platform.datasets`
        SET   join_key_type = @join_key_type,
              status        = 'ready',
              schema_source = @schema_source,
              updated_at    = CURRENT_TIMESTAMP()
        WHERE dataset_id    = @dataset_id
        """,
        [
            bigquery.ScalarQueryParameter("join_key_type", "STRING", join_key_type),
            bigquery.ScalarQueryParameter("schema_source", "STRING", schema_source),
            bigquery.ScalarQueryParameter("dataset_id",    "STRING", dataset_id),
        ],
    )


# ── Write: platform.dataset_columns ──────────────────────────────────────────


def insert_dataset_columns_rows(
    client: bigquery.Client,
    dataset_id: str,
    column_stats: list[dict[str, Any]],
) -> None:
    """
    Insert per-column rows into platform.dataset_columns (streaming insert).
    Called by the background processing task after parsing the uploaded file.
    semantic_name and description are null at this stage — filled in by PUT /schema.
    """
    rows = [
        {
            "dataset_id":    dataset_id,
            "column_name":   col["column_name"],
            "semantic_name": None,
            "description":   None,
            "data_type":     col["data_type"],
            "is_join_key":   False,           # updated by PUT /schema
            "null_rate":     col["null_rate"],
        }
        for col in column_stats
    ]
    _streaming_insert(client, f"{PROJECT}.platform.dataset_columns", rows)


def replace_dataset_columns(
    client: bigquery.Client,
    dataset_id: str,
    join_key_column_names: set[str],
    column_updates: list[dict[str, Any]],
) -> None:
    """
    Apply schema mapping: DELETE existing rows, INSERT updated rows.
    Called by PUT /api/v1/datasets/{id}/schema.

    column_updates is a list of {column_name, semantic_name, description, data_type,
    null_rate} dicts — null_rate is carried over from the existing rows.
    """
    # Step 1: DML DELETE (blocking, ~2s; immediately visible after completion).
    _run_dml(
        client,
        f"DELETE FROM `{PROJECT}.platform.dataset_columns` WHERE dataset_id = @dataset_id",
        [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
    )

    # Step 2: Streaming INSERT of updated rows.
    rows = [
        {
            "dataset_id":    dataset_id,
            "column_name":   col["column_name"],
            "semantic_name": col["semantic_name"],
            "description":   col["description"],
            "data_type":     col["data_type"],
            "is_join_key":   col["column_name"] in join_key_column_names,
            "null_rate":     col.get("null_rate", 0.0),
        }
        for col in column_updates
    ]
    _streaming_insert(client, f"{PROJECT}.platform.dataset_columns", rows)


def get_dataset_sample_rows(
    client: bigquery.Client,
    dataset_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Fetch the first `limit` rows from user_datasets.{sanitized_id}.

    Used by POST /infer-schema to give Claude real sample values.
    Returns an empty list if the table has no rows (not an error).

    Note: the table name is embedded via f-string (not parameterized) because
    BigQuery does not support parameterized table references.  The dataset_id
    is sanitized by _to_bq_table_name() which replaces hyphens with underscores
    — the only permitted characters in BQ table names — so this is safe.
    """
    bq_table = _to_bq_table_name(dataset_id)
    params = [bigquery.ScalarQueryParameter("lim", "INT64", limit)]
    query = f"SELECT * FROM `{PROJECT}.user_datasets.{bq_table}` LIMIT @lim"
    return _run_query(client, query, params)


def delete_dataset(client: bigquery.Client, dataset_id: str) -> None:
    """
    Delete a dataset: remove metadata rows and drop the user_datasets BQ table.
    Callers must verify the dataset is not referenced before calling this.
    """
    bq_table = _to_bq_table_name(dataset_id)

    # Delete metadata (DML — runs synchronously).
    _run_dml(
        client,
        f"DELETE FROM `{PROJECT}.platform.dataset_columns` WHERE dataset_id = @dataset_id",
        [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
    )
    _run_dml(
        client,
        f"DELETE FROM `{PROJECT}.platform.datasets` WHERE dataset_id = @dataset_id",
        [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
    )

    # Drop the user_datasets table (not_found_ok since it may not exist yet if
    # the background task was still running or errored before BQ load).
    try:
        client.delete_table(
            f"{PROJECT}.user_datasets.{bq_table}", not_found_ok=True
        )
        logger.info("Dropped user_datasets.%s", bq_table)
    except Exception as exc:
        logger.warning("Could not drop user_datasets.%s: %s", bq_table, exc)


def delete_dataset_registry_only(client: bigquery.Client, dataset_id: str) -> None:
    """
    Delete the registry row from platform.datasets (and its column rows).
    Does NOT drop the user_datasets BigQuery table — registry-only delete
    for the P5-03 DELETE endpoint which must not cascade.

    Callers are responsible for the GCS file delete (separate step).
    """
    # Delete column metadata first (FK-like dependency).
    _run_dml(
        client,
        f"DELETE FROM `{PROJECT}.platform.dataset_columns` WHERE dataset_id = @dataset_id",
        [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
    )
    # Delete the main registry row.
    _run_dml(
        client,
        f"DELETE FROM `{PROJECT}.platform.datasets` WHERE dataset_id = @dataset_id",
        [bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)],
    )


def delete_dataset_gcs_file(dataset_id: str) -> None:
    """
    Attempt to delete the raw upload file from GCS bucket 'nfl-model-471509-uploads'.
    Path pattern: datasets/{dataset_id}.*

    Logs a warning and returns without raising if the file is not found or
    the delete fails — the database row is the canonical state.
    """
    try:
        from google.cloud import storage as gcs_storage
        storage_client = gcs_storage.Client()
        bucket = storage_client.bucket(f"{PROJECT}-uploads")
        blobs = list(bucket.list_blobs(prefix=f"datasets/{dataset_id}"))
        if not blobs:
            logger.info(
                "GCS: no upload file found for dataset %s (already cleaned up or never uploaded)",
                dataset_id,
            )
            return
        for blob in blobs:
            blob.delete()
            logger.info("GCS: deleted upload file %s for dataset %s", blob.name, dataset_id)
    except Exception as exc:
        logger.warning(
            "GCS file delete failed for dataset %s (non-fatal): %s", dataset_id, exc
        )


# ── File processing (called inside the background task) ───────────────────────


ALLOWED_EXTENSIONS: set[str] = {"csv", "xlsx", "xls", "json"}
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024   # 50 MB


def parse_file(content: bytes, ext: str) -> pd.DataFrame:
    """
    Parse uploaded file content into a pandas DataFrame.
    Raises ValueError for unsupported extensions or malformed files.
    """
    buf = io.BytesIO(content)
    ext = ext.lower().lstrip(".")

    if ext == "csv":
        return pd.read_csv(buf)
    elif ext in ("xlsx", "xls"):
        return pd.read_excel(buf, engine="openpyxl" if ext == "xlsx" else None)
    elif ext == "json":
        # Expect an array of objects.
        return pd.read_json(buf, orient="records")
    else:
        raise ValueError(f"Unsupported file extension: {ext!r}")


def compute_column_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Infer data type and compute null rate for each column in a DataFrame.

    Returns a list of dicts with keys:
      column_name, data_type ("numeric" | "categorical" | "boolean"), null_rate
    """
    stats = []
    for col in df.columns:
        series = df[col]
        n = len(series)

        if pd.api.types.is_bool_dtype(series):
            data_type = "boolean"
        elif pd.api.types.is_numeric_dtype(series):
            data_type = "numeric"
        else:
            data_type = "categorical"

        null_rate = float(series.isna().sum() / n) if n > 0 else 0.0
        stats.append({
            "column_name": str(col),
            "data_type":   data_type,
            "null_rate":   round(null_rate, 6),
        })
    return stats


def load_dataframe_to_bigquery(
    client: bigquery.Client,
    dataset_id: str,
    df: pd.DataFrame,
) -> None:
    """
    Load a pandas DataFrame into BigQuery as user_datasets.{sanitized_id}.
    Creates the table if it doesn't exist (autodetect=True).
    """
    bq_table = _to_bq_table_name(dataset_id)
    table_ref = f"{PROJECT}.user_datasets.{bq_table}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()   # block until load completes
    logger.info(
        "Loaded %d rows / %d columns into %s", len(df), len(df.columns), table_ref
    )


# ── Cloud Run Job trigger ─────────────────────────────────────────────────────


def trigger_dataset_processor(dataset_id: str, file_ext: str) -> None:
    """
    Trigger the Cloud Run Job for the dataset upload processor.

    Makes a direct HTTP call to the Cloud Run Jobs API to execute the
    nfl-dataset-processor job with environment variable overrides for
    DATASET_ID and FILE_EXT.

    Args:
        dataset_id: UUID of the dataset row already inserted into platform.datasets.
        file_ext:   File extension without dot — csv | xlsx | xls | json.
    """
    import google.auth
    import google.auth.transport.requests
    import requests as http_requests

    try:
        credentials, project = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())

        region = "us-central1"
        job_name = "nfl-dataset-processor"
        url = (
            f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/"
            f"namespaces/{project}/jobs/{job_name}:run"
        )

        payload = {
            "overrides": {
                "containerOverrides": [{
                    "env": [
                        {"name": "DATASET_ID", "value": dataset_id},
                        {"name": "FILE_EXT",   "value": file_ext},
                    ]
                }]
            }
        }

        resp = http_requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10,
        )
        resp.raise_for_status()

        execution_name = resp.json().get("metadata", {}).get("name", "unknown")
        logger.info(
            "Cloud Run Job execution created for dataset %s (ext=%s): %s",
            dataset_id, file_ext, execution_name,
        )
    except Exception as exc:
        logger.error(
            "Failed to trigger dataset processor for %s (ext=%s): %s",
            dataset_id, file_ext, exc, exc_info=True,
        )
        raise


# ── Background task (kept for local dev / testing — not used in production) ───


def process_upload_background(
    dataset_id: str,
    file_content: bytes,
    file_ext: str,
    bq_client: bigquery.Client,
) -> None:
    """
    Run synchronously in a FastAPI BackgroundTask after the 202 is returned.

    Steps:
      1. Parse the file into a DataFrame.
      2. Load the DataFrame to BigQuery as user_datasets.{dataset_id}.
      3. Compute per-column null rates and type inference.
      4. Insert rows into platform.dataset_columns.
      5. Update platform.datasets: status='mapping', row_count, column_count.

    On any failure, update status to 'error' and log with dataset_id.
    """
    try:
        logger.info("[dataset=%s] Starting background processing", dataset_id)

        df = parse_file(file_content, file_ext)
        logger.info("[dataset=%s] Parsed %d rows × %d cols", dataset_id, len(df), len(df.columns))

        load_dataframe_to_bigquery(bq_client, dataset_id, df)

        col_stats = compute_column_stats(df)
        insert_dataset_columns_rows(bq_client, dataset_id, col_stats)

        update_dataset_after_processing(
            bq_client,
            dataset_id,
            status="mapping",
            row_count=len(df),
            column_count=len(df.columns),
        )
        logger.info("[dataset=%s] Background processing complete", dataset_id)

    except Exception as exc:
        logger.error(
            "[dataset=%s] Background processing failed: %s", dataset_id, exc, exc_info=True
        )
        try:
            update_dataset_after_processing(bq_client, dataset_id, "error", None, None)
        except Exception as update_exc:
            logger.error(
                "[dataset=%s] Could not update status to 'error': %s", dataset_id, update_exc
            )

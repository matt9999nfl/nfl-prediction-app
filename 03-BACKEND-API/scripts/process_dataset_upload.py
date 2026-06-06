#!/usr/bin/env python3
"""
Dataset upload processor — Cloud Run Job entry point.

Reads the uploaded file from GCS, parses it, loads it to BigQuery as
user_datasets.{dataset_id}, computes column stats, and updates
platform.datasets status to 'mapping' (or 'error' on failure).

Environment variables (all required):
  DATASET_ID          UUID of the dataset row already inserted by the API.
  FILE_EXT            File extension without dot: csv | xlsx | xls | json
  BIGQUERY_PROJECT    GCP project ID (default: nfl-model-471509)

The GCS object is read from:
  gs://nfl-model-471509-uploads/{DATASET_ID}/raw.{FILE_EXT}

Exit codes:
  0 — processing complete (status set to 'mapping')
  1 — unrecoverable failure (status set to 'error')

Cloud Run Jobs retry on non-zero exit — at most once (max-retries=1 in
Terraform). The processing logic is idempotent: WRITE_TRUNCATE is used
for the BQ load, and column rows are deleted before re-insert.
"""
import io
import logging
import os
import sys

import pandas as pd
from google.cloud import bigquery, storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────

DATASET_ID = os.environ.get("DATASET_ID", "").strip()
FILE_EXT = os.environ.get("FILE_EXT", "").strip().lower().lstrip(".")
PROJECT = os.environ.get("BIGQUERY_PROJECT", "nfl-model-471509").strip()
BUCKET_NAME = "nfl-model-471509-uploads"


def _validate_env() -> None:
    missing = [v for v in ("DATASET_ID", "FILE_EXT") if not os.environ.get(v, "").strip()]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
    if FILE_EXT not in {"csv", "xlsx", "xls", "json"}:
        raise ValueError(f"Unsupported FILE_EXT: '{FILE_EXT}'. Allowed: csv, xlsx, xls, json")


# ── GCS download ──────────────────────────────────────────────────────────────


def download_from_gcs() -> bytes:
    blob_name = f"{DATASET_ID}/raw.{FILE_EXT}"
    logger.info("Downloading gs://%s/%s", BUCKET_NAME, blob_name)
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)
    content = blob.download_as_bytes()
    logger.info("Downloaded %d bytes", len(content))
    return content


# ── File parsing ──────────────────────────────────────────────────────────────


def parse_file(content: bytes, ext: str) -> pd.DataFrame:
    buf = io.BytesIO(content)
    if ext == "csv":
        return pd.read_csv(buf)
    elif ext in ("xlsx", "xls"):
        return pd.read_excel(buf, engine="openpyxl" if ext == "xlsx" else None)
    elif ext == "json":
        return pd.read_json(buf, orient="records")
    else:
        raise ValueError(f"Unsupported extension: {ext!r}")


# ── Column stats ──────────────────────────────────────────────────────────────


def compute_column_stats(df: pd.DataFrame) -> list[dict]:
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
            "data_type": data_type,
            "null_rate": round(null_rate, 6),
        })
    return stats


# ── BigQuery helpers ──────────────────────────────────────────────────────────


def _to_bq_table_name(dataset_id: str) -> str:
    return dataset_id.replace("-", "_")


def load_dataframe_to_bigquery(bq: bigquery.Client, df: pd.DataFrame) -> None:
    bq_table = _to_bq_table_name(DATASET_ID)
    table_ref = f"{PROJECT}.user_datasets.{bq_table}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = bq.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    logger.info("Loaded %d rows / %d cols into %s", len(df), len(df.columns), table_ref)


def insert_column_rows(bq: bigquery.Client, col_stats: list[dict]) -> None:
    # Delete existing rows first (idempotent retry safety).
    bq.query(
        f"DELETE FROM `{PROJECT}.platform.dataset_columns` WHERE dataset_id = @dataset_id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("dataset_id", "STRING", DATASET_ID),
        ]),
    ).result()

    rows = [
        {
            "dataset_id": DATASET_ID,
            "column_name": col["column_name"],
            "semantic_name": None,
            "description": None,
            "data_type": col["data_type"],
            "is_join_key": False,
            "null_rate": col["null_rate"],
        }
        for col in col_stats
    ]
    errors = bq.insert_rows_json(f"{PROJECT}.platform.dataset_columns", rows)
    if errors:
        raise RuntimeError(f"BigQuery streaming insert errors: {errors}")
    logger.info("Inserted %d column rows for dataset %s", len(rows), DATASET_ID)


def update_dataset_status(bq: bigquery.Client, status: str, row_count=None, column_count=None) -> None:
    bq.query(
        f"""
        UPDATE `{PROJECT}.platform.datasets`
        SET   status       = @status,
              row_count    = @row_count,
              column_count = @column_count,
              updated_at   = CURRENT_TIMESTAMP()
        WHERE dataset_id   = @dataset_id
        """,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("status",       "STRING", status),
            bigquery.ScalarQueryParameter("row_count",    "INT64",  row_count),
            bigquery.ScalarQueryParameter("column_count", "INT64",  column_count),
            bigquery.ScalarQueryParameter("dataset_id",   "STRING", DATASET_ID),
        ]),
    ).result()
    logger.info("Updated dataset %s status → %s", DATASET_ID, status)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    logger.info("Dataset upload processor starting (dataset_id=%s ext=%s)", DATASET_ID, FILE_EXT)

    bq = bigquery.Client(project=PROJECT)

    try:
        content = download_from_gcs()

        df = parse_file(content, FILE_EXT)
        logger.info("Parsed %d rows × %d cols", len(df), len(df.columns))

        load_dataframe_to_bigquery(bq, df)

        col_stats = compute_column_stats(df)
        insert_column_rows(bq, col_stats)

        update_dataset_status(bq, "mapping", row_count=len(df), column_count=len(df.columns))
        logger.info("Dataset %s processing complete", DATASET_ID)

    except Exception as exc:
        logger.error("Dataset %s processing failed: %s", DATASET_ID, exc, exc_info=True)
        try:
            update_dataset_status(bq, "error")
        except Exception as update_exc:
            logger.error("Could not update dataset %s status to error: %s", DATASET_ID, update_exc)
        sys.exit(1)


if __name__ == "__main__":
    _validate_env()
    main()

"""
Task 3 — Ingest nflfastR weekly rosters → raw_nflfastr.rosters

Usage:
    python scripts/ingest_rosters.py [--seasons 2015,2016,...] [--season 2024]
"""
import argparse
import logging
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, ".")

from google.cloud import bigquery

from adapters.nflfastr import NflfastrAdapter
from scripts.bq_utils import (
    PROJECT,
    ensure_datasets,
    ensure_table_with_schema,
    get_client,
    load_df_to_bq,
    normalize_dtypes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TABLE = "raw_nflfastr.rosters"
CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
DEFAULT_SEASONS = list(range(2015, CURRENT_SEASON + 1))

SCHEMA = [
    bigquery.SchemaField("season", "INTEGER"),
    bigquery.SchemaField("team", "STRING"),
    bigquery.SchemaField("week", "FLOAT"),  # load_df_to_bq normalises int64→float64
]


def ingest_season(client: bigquery.Client, adapter: NflfastrAdapter, season: int) -> dict:
    t0 = time.time()
    logger.info(f"=== Rosters season {season} ===")

    df = adapter.fetch_rosters(season)
    result = adapter.validate_rosters(df, season)
    logger.info(str(result))
    if not result.passed:
        logger.error(f"Validation FAILED for rosters {season} — skipping load")
        return {"season": season, "rows": 0, "status": "VALIDATION_FAILED", "errors": result.errors}

    df["season"] = season

    # Pre-coerce numeric roster columns to float64 before normalize_dtypes.
    # These columns are logically numeric but come as object dtype in some seasons
    # (non-numeric sentinel values or pandas dtype inference). Without this step,
    # BQ locks the column as STRING in early seasons and rejects FLOAT in later ones.
    _NUMERIC_ROSTER_COLS = ["draft_number", "draft_round", "height", "weight", "years_exp"]
    for col in _NUMERIC_ROSTER_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = normalize_dtypes(df)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )
    full_table = f"{PROJECT}.{TABLE}${season}"
    load_df_to_bq(client, df, full_table, job_config)

    elapsed = round(time.time() - t0, 1)
    logger.info(f"Rosters {season}: loaded {len(df)} rows in {elapsed}s")
    return {"season": season, "rows": len(df), "status": "OK", "elapsed_s": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Ingest nflfastR rosters into BigQuery")
    parser.add_argument("--seasons", help="Comma-separated list e.g. 2015,2016")
    parser.add_argument("--season", type=int, help="Single season (incremental mode)")
    args = parser.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = [int(s) for s in args.seasons.split(",")]
    else:
        seasons = DEFAULT_SEASONS

    logger.info(f"Ingesting rosters for seasons: {seasons}")

    client = get_client()
    ensure_datasets(client, ["raw_nflfastr"])
    ensure_table_with_schema(
        client, TABLE, SCHEMA,
        partition_field="season",
        clustering_fields=None,
    )

    adapter = NflfastrAdapter()
    results = []
    for season in seasons:
        r = ingest_season(client, adapter, season)
        results.append(r)

    print("\n=== Rosters Ingest Summary ===")
    total_rows = 0
    for r in results:
        rows = r.get("rows", 0)
        total_rows += rows
        print(f"  {r['season']}: {rows:>7,} rows  [{r['status']}]")
    print(f"  TOTAL: {total_rows:,} rows across {len(results)} seasons")

    failed = [r for r in results if r["status"] != "OK"]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

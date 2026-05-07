"""
Task 2 — Ingest nflfastR schedules → raw_nflfastr.schedules

Usage:
    python scripts/ingest_schedules.py [--seasons 2015,2016,...] [--season 2024]
"""
import argparse
import logging
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")

from google.cloud import bigquery

from adapters.nflfastr import NflfastrAdapter
from scripts.bq_utils import (
    PROJECT,
    ensure_datasets,
    ensure_table_with_schema,
    get_client,
    normalize_dtypes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TABLE = "raw_nflfastr.schedules"
CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
DEFAULT_SEASONS = list(range(2015, CURRENT_SEASON + 1))

SCHEMA = [
    bigquery.SchemaField("season", "INTEGER"),
    bigquery.SchemaField("game_id", "STRING"),
    bigquery.SchemaField("home_team", "STRING"),
    bigquery.SchemaField("away_team", "STRING"),
]


def ingest_season(client: bigquery.Client, adapter: NflfastrAdapter, season: int) -> dict:
    t0 = time.time()
    logger.info(f"=== Schedules season {season} ===")

    df = adapter.fetch_schedules(season)
    result = adapter.validate_schedules(df, season)
    logger.info(str(result))
    if not result.passed:
        logger.error(f"Validation FAILED for schedules {season} — skipping load")
        return {"season": season, "rows": 0, "status": "VALIDATION_FAILED", "errors": result.errors}

    df["season"] = season
    df = normalize_dtypes(df)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )
    full_table = f"{PROJECT}.{TABLE}${season}"
    job = client.load_table_from_dataframe(df, full_table, job_config=job_config)
    job.result()

    elapsed = round(time.time() - t0, 1)
    logger.info(f"Schedules {season}: loaded {len(df)} rows in {elapsed}s")
    return {"season": season, "rows": len(df), "status": "OK", "elapsed_s": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Ingest nflfastR schedules into BigQuery")
    parser.add_argument("--seasons", help="Comma-separated list e.g. 2015,2016")
    parser.add_argument("--season", type=int, help="Single season (incremental mode)")
    args = parser.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = [int(s) for s in args.seasons.split(",")]
    else:
        seasons = DEFAULT_SEASONS

    logger.info(f"Ingesting schedules for seasons: {seasons}")

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

    print("\n=== Schedules Ingest Summary ===")
    total_rows = 0
    for r in results:
        rows = r.get("rows", 0)
        total_rows += rows
        print(f"  {r['season']}: {rows:>5,} rows  [{r['status']}]")
    print(f"  TOTAL: {total_rows:,} rows across {len(results)} seasons")

    failed = [r for r in results if r["status"] != "OK"]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

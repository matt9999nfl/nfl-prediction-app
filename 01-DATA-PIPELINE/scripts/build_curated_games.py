"""
Task 5 — Build curated.games from raw_nflfastr.schedules.

Filters to REG season, joins closing lines, derives home_covered.
Exact schema per PIPELINE_SPEC_PHASE1.md.

Usage:
    python scripts/build_curated_games.py [--seasons 2015,2016,...] [--season 2024]

Prerequisite: ingest_schedules.py must have completed successfully.
"""
import argparse
import logging
import sys
from datetime import datetime

sys.path.insert(0, ".")

from google.cloud import bigquery

from scripts.bq_utils import PROJECT, ensure_datasets, ensure_table_with_schema, get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
DEFAULT_SEASONS = list(range(2015, CURRENT_SEASON + 1))

CURATED_TABLE = "curated.games"

# Exact schema from spec
SCHEMA = [
    bigquery.SchemaField("game_id",           "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("season",             "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("week",               "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("game_date",          "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("home_team",          "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("away_team",          "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("home_score",         "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("away_score",         "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("home_spread_close",  "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("total_close",        "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("home_covered",       "BOOLEAN", mode="NULLABLE"),
    bigquery.SchemaField("season_type",        "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("roof",               "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("surface",            "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("div_game",           "BOOLEAN", mode="NULLABLE"),
    bigquery.SchemaField("stadium",            "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("temp",               "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("wind",               "FLOAT",   mode="NULLABLE"),
]

# Raw→curated column mapping (nflfastR name → curated name)
COL_MAP = {
    "game_id":      "game_id",
    "season":       "season",
    "week":         "week",
    "gameday":      "game_date",      # nflfastR uses 'gameday'
    "home_team":    "home_team",
    "away_team":    "away_team",
    "home_score":   "home_score",
    "away_score":   "away_score",
    "spread_line":  "home_spread_close",
    "total_line":   "total_close",
    "game_type":    "season_type",    # nflfastR uses 'game_type'
    "roof":         "roof",
    "surface":      "surface",
    "div_game":     "div_game",
    "stadium":      "stadium",
    "temp":         "temp",
    "wind":         "wind",
}

# Fallback if nflfastR uses alternate column names
ALT_COL_MAP = {
    "season_type": "season_type",     # some versions use season_type
    "game_date":   "game_date",       # some versions use game_date directly
}


def derive_home_covered(home_score, away_score, home_spread_close):
    """
    home_covered = True  if (home_score - away_score) > -home_spread_close
                 = False if (home_score - away_score) < -home_spread_close
                 = None  if push (exactly equal) or any value is null
    """
    import pandas as pd
    import numpy as np

    margin = home_score - away_score
    required_margin = -home_spread_close

    covered = pd.Series([None] * len(margin), dtype=object)
    both_valid = margin.notna() & required_margin.notna()

    covered[both_valid & (margin > required_margin)] = True
    covered[both_valid & (margin < required_margin)] = False
    # push (margin == required_margin) stays None

    return covered


def build_season(client: bigquery.Client, season: int) -> dict:
    logger.info(f"=== Building curated.games for season {season} ===")

    query = f"""
        SELECT *
        FROM `{PROJECT}.raw_nflfastr.schedules`
        WHERE season = {season}
    """
    df = client.query(query).to_dataframe()
    logger.info(f"  Loaded {len(df)} raw schedule rows for {season}")

    # Determine season_type column name
    if "game_type" in df.columns:
        df = df[df["game_type"] == "REG"].copy()
        df.rename(columns={"game_type": "season_type"}, inplace=True)
    elif "season_type" in df.columns:
        df = df[df["season_type"] == "REG"].copy()
    else:
        logger.error(f"No game_type or season_type column in schedules — cannot filter to REG")
        return {"season": season, "rows": 0, "status": "ERROR"}

    logger.info(f"  {len(df)} REG games for {season}")

    # Normalize game_date column
    if "gameday" in df.columns and "game_date" not in df.columns:
        df.rename(columns={"gameday": "game_date"}, inplace=True)

    # Rename spread/total columns
    if "spread_line" in df.columns:
        df.rename(columns={"spread_line": "home_spread_close"}, inplace=True)
    if "total_line" in df.columns:
        df.rename(columns={"total_line": "total_close"}, inplace=True)

    # Derive home_covered
    if "home_spread_close" in df.columns and "home_score" in df.columns:
        import pandas as pd
        home_score = pd.to_numeric(df["home_score"], errors="coerce")
        away_score = pd.to_numeric(df["away_score"], errors="coerce")
        spread = pd.to_numeric(df["home_spread_close"], errors="coerce")
        df["home_covered"] = derive_home_covered(home_score, away_score, spread)
    else:
        df["home_covered"] = None

    # Enforce season_type = 'REG' constant
    df["season_type"] = "REG"

    # Keep only curated schema columns that exist
    curated_cols = [f.name for f in SCHEMA]
    available = [c for c in curated_cols if c in df.columns]
    missing = [c for c in curated_cols if c not in df.columns]
    if missing:
        logger.warning(f"  Missing columns (will be NULL): {missing}")
        for c in missing:
            df[c] = None

    df = df[curated_cols].copy()

    # Type coercions
    import pandas as pd
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    for int_col in ["season", "week", "home_score", "away_score"]:
        df[int_col] = pd.to_numeric(df[int_col], errors="coerce")
    for float_col in ["home_spread_close", "total_close", "temp", "wind"]:
        df[float_col] = pd.to_numeric(df[float_col], errors="coerce")
    for bool_col in ["div_game"]:
        if df[bool_col].dtype == object:
            df[bool_col] = df[bool_col].map({"True": True, "False": False, "1": True, "0": False})

    # Load to BQ
    full_table = f"{PROJECT}.{CURATED_TABLE}${season}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=SCHEMA,
    )
    job = client.load_table_from_dataframe(df, full_table, job_config=job_config)
    job.result()

    logger.info(f"  curated.games {season}: loaded {len(df)} rows")
    return {"season": season, "rows": len(df), "status": "OK"}


def main():
    parser = argparse.ArgumentParser(description="Build curated.games")
    parser.add_argument("--seasons", help="Comma-separated seasons")
    parser.add_argument("--season", type=int)
    args = parser.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = [int(s) for s in args.seasons.split(",")]
    else:
        seasons = DEFAULT_SEASONS

    client = get_client()
    ensure_datasets(client, ["curated"])
    ensure_table_with_schema(
        client, CURATED_TABLE, SCHEMA,
        partition_field="season",
        clustering_fields=["home_team", "away_team"],
    )

    results = []
    for season in seasons:
        r = build_season(client, season)
        results.append(r)

    print("\n=== curated.games Build Summary ===")
    for r in results:
        print(f"  {r['season']}: {r.get('rows', 0):>5,} rows  [{r['status']}]")

    failed = [r for r in results if r["status"] != "OK"]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

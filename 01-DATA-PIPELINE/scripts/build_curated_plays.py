"""
Task 6 — Build curated.plays from raw_nflfastr.pbp.

Filters to REG season only. Selects spec columns. Checks referential integrity
against curated.games. Boolean columns default to False (not null) per spec.

Usage:
    python scripts/build_curated_plays.py [--seasons 2015,2016,...] [--season 2024]

Prerequisite: ingest_pbp.py and build_curated_games.py must have completed.
"""
import argparse
import logging
import sys
from datetime import datetime

sys.path.insert(0, ".")

import pandas as pd
from google.cloud import bigquery

from scripts.bq_utils import PROJECT, ensure_datasets, ensure_table_with_schema, get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
DEFAULT_SEASONS = list(range(2015, CURRENT_SEASON + 1))

CURATED_TABLE = "curated.plays"

# Exact schema from spec
SCHEMA = [
    bigquery.SchemaField("play_id",              "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("game_id",              "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("season",               "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("week",                 "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("posteam",              "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("defteam",              "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("play_type",            "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("down",                 "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("ydstogo",              "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("yardline_100",         "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("yards_gained",         "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("epa",                  "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("wpa",                  "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("qb_hit",               "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("sack",                 "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("touchdown",            "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("interception",         "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("fumble",               "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("fumble_lost",          "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("cpoe",                 "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("air_yards",            "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("yards_after_catch",    "FLOAT",   mode="NULLABLE"),
    bigquery.SchemaField("score_differential",   "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("game_half",            "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("passer_player_id",     "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("passer_player_name",   "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("rusher_player_id",     "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("rusher_player_name",   "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("receiver_player_id",   "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("receiver_player_name", "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("penalty",              "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("penalty_type",         "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("penalty_team",         "STRING",  mode="NULLABLE"),
]

# Columns that must default to False (not null) per spec
BOOL_DEFAULT_FALSE = [
    "qb_hit", "sack", "touchdown", "interception",
    "fumble", "fumble_lost", "penalty",
]

# nflfastR raw column → curated column name (only where name differs)
RENAME_MAP = {
    # nflfastR uses same names for most; these are the exceptions
    # (nothing needs renaming in current nflfastR schema)
}


def build_season(client: bigquery.Client, season: int) -> dict:
    logger.info(f"=== Building curated.plays for season {season} ===")

    curated_col_names = [f.name for f in SCHEMA]

    # Pull REG-season plays from raw PBP joined to curated.games for RI check
    cols_select = ", ".join(f"p.{c}" for c in curated_col_names if c in [
        "play_id","game_id","season","week","posteam","defteam","play_type",
        "down","ydstogo","yardline_100","yards_gained","epa","wpa",
        "qb_hit","sack","touchdown","interception","fumble","fumble_lost",
        "cpoe","air_yards","yards_after_catch","score_differential","game_half",
        "passer_player_id","passer_player_name","rusher_player_id","rusher_player_name",
        "receiver_player_id","receiver_player_name","penalty","penalty_type","penalty_team",
    ])

    query = f"""
        SELECT
            p.play_id,
            p.game_id,
            p.season,
            p.week,
            p.posteam,
            p.defteam,
            p.play_type,
            p.down,
            p.ydstogo,
            p.yardline_100,
            p.yards_gained,
            p.epa,
            p.wpa,
            p.qb_hit,
            p.sack,
            p.touchdown,
            p.interception,
            p.fumble,
            p.fumble_lost,
            p.cpoe,
            p.air_yards,
            p.yards_after_catch,
            p.score_differential,
            p.game_half,
            p.passer_player_id,
            p.passer_player_name,
            p.rusher_player_id,
            p.rusher_player_name,
            p.receiver_player_id,
            p.receiver_player_name,
            p.penalty,
            p.penalty_type,
            p.penalty_team
        FROM `{PROJECT}.raw_nflfastr.pbp` p
        INNER JOIN `{PROJECT}.curated.games` g
            ON p.game_id = g.game_id
        WHERE p.season = {season}
          AND g.season_type = 'REG'
    """
    df = client.query(query).to_dataframe()
    logger.info(f"  {len(df)} plays loaded for {season} (REG, joined to curated.games)")

    if len(df) == 0:
        logger.warning(f"  No plays for season {season} — skipping")
        return {"season": season, "rows": 0, "status": "EMPTY"}

    # Boolean columns: fill nulls with False per spec
    for col in BOOL_DEFAULT_FALSE:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(bool)
        else:
            df[col] = False
            logger.warning(f"  Column '{col}' not in PBP — defaulting to False")

    # Drop non-play rows: timeouts, end-of-quarter markers, and other administrative
    # rows have null posteam/defteam and must be excluded before loading to BQ
    # since those columns are REQUIRED in the schema.
    before = len(df)
    df = df[df["posteam"].notna() & df["defteam"].notna()].copy()
    dropped = before - len(df)
    if dropped:
        logger.info(f"  Dropped {dropped} non-play rows (null posteam/defteam)")

    # Ensure required non-null columns have no nulls (post-filter sanity check)
    for col in ["play_id", "game_id", "season", "week", "posteam", "defteam", "play_type"]:
        null_count = df[col].isna().sum()
        if null_count > 0:
            logger.warning(f"  {null_count} nulls in REQUIRED column '{col}'")

    # play_type: fill missing with 'no_play'
    df["play_type"] = df["play_type"].fillna("no_play")

    # Type coercions
    for int_col in ["play_id", "season", "week", "down", "ydstogo", "yardline_100", "yards_gained", "score_differential"]:
        if int_col in df.columns:
            df[int_col] = pd.to_numeric(df[int_col], errors="coerce")
    for float_col in ["epa", "wpa", "cpoe", "air_yards", "yards_after_catch"]:
        if float_col in df.columns:
            df[float_col] = pd.to_numeric(df[float_col], errors="coerce")

    # Add any missing optional columns as None
    for field in SCHEMA:
        if field.name not in df.columns:
            df[field.name] = None

    df = df[curated_col_names].copy()

    # Row count validation
    expected_min = 35_000
    expected_max = 60_000
    if len(df) < expected_min:
        logger.warning(f"  Row count {len(df)} below expected min {expected_min}")
    elif len(df) > expected_max:
        logger.warning(f"  Row count {len(df)} above expected max {expected_max}")

    # Load to BQ
    full_table = f"{PROJECT}.{CURATED_TABLE}${season}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=SCHEMA,
    )
    job = client.load_table_from_dataframe(df, full_table, job_config=job_config)
    job.result()

    logger.info(f"  curated.plays {season}: loaded {len(df)} rows")
    return {"season": season, "rows": len(df), "status": "OK"}


def main():
    parser = argparse.ArgumentParser(description="Build curated.plays")
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
        clustering_fields=["game_id", "posteam"],
    )

    results = []
    for season in seasons:
        r = build_season(client, season)
        results.append(r)

    print("\n=== curated.plays Build Summary ===")
    for r in results:
        print(f"  {r['season']}: {r.get('rows', 0):>7,} rows  [{r['status']}]")

    failed = [r for r in results if r["status"] not in ("OK", "EMPTY")]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

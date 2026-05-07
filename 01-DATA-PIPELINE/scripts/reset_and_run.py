# Drop any partially-loaded raw tables and run the full Phase 1 pipeline.
# Single-process, no subprocess calls, no working-directory games.
import sys
import os
import argparse
import logging
import time
import warnings
from datetime import datetime
from pathlib import Path

# Suppress noisy pandas-gbq FutureWarning and BQ type warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="google.cloud.bigquery")

# Root of 01-DATA-PIPELINE on the path so all imports work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(ROOT / "pipeline.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
SEASONS = list(range(2015, CURRENT_SEASON + 1))

from google.cloud import bigquery
from google.cloud.exceptions import NotFound
import nfl_data_py as nfl
import pandas as pd

from scripts.bq_utils import (
    PROJECT, get_client, ensure_datasets,
    ensure_table_with_schema, normalize_dtypes,
)
from adapters.nflfastr import NflfastrAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def drop(client, table_ref):
    full = f"{PROJECT}.{table_ref}"
    try:
        client.delete_table(full)
        log.info(f"Dropped: {full}")
    except NotFound:
        log.info(f"Not found (skip drop): {full}")


def bq_load(client, df, full_table, schema=None):
    """Load a DataFrame partition to BQ with WRITE_TRUNCATE."""
    if schema:
        cfg = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=schema,
        )
    else:
        cfg = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=True,
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        )
    job = client.load_table_from_dataframe(df, full_table, job_config=cfg)
    job.result()


def normalize_for_raw(df: pd.DataFrame, keep_int: list = None) -> pd.DataFrame:
    """
    Normalize dtypes for a raw landing table so BQ sees consistent types
    across all seasons:
    - object  -> str, null sentinels -> "", so BQ always detects STRING
    - int64   -> float64 (unless in keep_int), so BQ always detects FLOAT
                 (avoids INTEGER vs FLOAT conflicts when later seasons introduce
                 NaN into previously all-integer columns, e.g. n_offense)
    - float64 all-null -> object filled with "", so BQ detects STRING not INTEGER

    keep_int: list of column names to preserve as int64 (columns explicitly
              typed INTEGER in the table schema, e.g. 'season', 'week')
    """
    df = df.copy()
    protected = set(keep_int or [])
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str)
            df[col] = df[col].where(~df[col].isin(["nan", "None", "NaT", "<NA>", "none"]), "")
        elif col not in protected and (df[col].dtype == "int64" or df[col].dtype == "int32"):
            # Upcast to float64 so seasons with NaN values in the same column
            # don't cause INTEGER vs FLOAT type conflicts in BQ.
            df[col] = df[col].astype("float64")
        elif df[col].dtype == "float64" and df[col].isna().all():
            # All-null float: force to string so BQ detects STRING, not INTEGER
            df[col] = df[col].astype(object).fillna("")
    return df


def coerce_to_bq_schema(client, df: pd.DataFrame, full_table: str) -> pd.DataFrame:
    """
    For columns that already exist in the BQ table, coerce their pandas dtype
    to match the established BQ type. This prevents 'Field X has changed type'
    errors when a later season's raw data comes back with a different dtype
    (e.g. ngs_air_yards is FLOAT in BQ but pandas reads 2023 data as object
    because the source has some literal 'NA' strings mixed with floats).

    full_table: fully-qualified BQ table ref, e.g.
                'nfl-model-471509.raw_nflfastr.pbp'
    """
    try:
        table = client.get_table(full_table)
        bq_types = {f.name: f.field_type for f in table.schema}
    except Exception:
        return df  # table doesn't exist yet; nothing to coerce

    df = df.copy()
    for col in df.columns:
        if col not in bq_types:
            continue  # new column – let autodetect handle it
        bq_type = bq_types[col]
        if bq_type in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
            if df[col].dtype == object:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        elif bq_type in ("INTEGER", "INT64"):
            if df[col].dtype == object:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        elif bq_type == "STRING":
            if df[col].dtype != object:
                df[col] = df[col].astype(str)
            df[col] = df[col].astype(str)
            df[col] = df[col].where(
                ~df[col].isin(["nan", "None", "NaT", "<NA>", "none"]), ""
            )
        # BOOLEAN, DATE, TIMESTAMP: leave as-is; normalize_for_raw already handled them
    return df


def section(title):
    log.info("")
    log.info("=" * 60)
    log.info(f"  {title}")
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pbp-start", type=int, default=2015,
        help="Resume PBP ingest from this season (skips drop; use when earlier "
             "seasons are already loaded). Default: 2015 (full re-ingest)."
    )
    args = parser.parse_args()
    pbp_start = args.pbp_start

    t0 = time.time()
    client = get_client()
    adapter = NflfastrAdapter()

    ensure_datasets(client, ["raw_nflfastr", "raw_lines", "curated"])

    # -----------------------------------------------------------------------
    # TASK 2: raw_nflfastr.schedules
    # -----------------------------------------------------------------------
    section("TASK 2 - raw_nflfastr.schedules")
    drop(client, "raw_nflfastr.schedules")
    # Declare nfl_detail_id as STRING explicitly so BQ never auto-detects it
    # as INTEGER from null-only early seasons.
    ensure_table_with_schema(
        client, "raw_nflfastr.schedules",
        [bigquery.SchemaField("season",        "INTEGER"),
         bigquery.SchemaField("game_id",        "STRING"),
         bigquery.SchemaField("home_team",      "STRING"),
         bigquery.SchemaField("away_team",      "STRING"),
         bigquery.SchemaField("nfl_detail_id",  "STRING")],
        partition_field="season",
    )
    log.info("Fetching all schedule seasons at once...")
    all_sched = nfl.import_schedules(years=SEASONS)
    all_sched = normalize_for_raw(all_sched, keep_int=["season"])

    sched_totals = {}
    season_col = "season" if "season" in all_sched.columns else "year"
    for s in SEASONS:
        df = all_sched[all_sched[season_col] == s].copy()
        df["source"] = "nflfastR"
        df["license_tag"] = "open"
        bq_load(client, df, f"{PROJECT}.raw_nflfastr.schedules${s}")
        sched_totals[s] = len(df)
        log.info(f"  OK raw_nflfastr.schedules${s} - {len(df):,} rows")

    # -----------------------------------------------------------------------
    # TASK 4: Closing Line Audit (inline, uses already-fetched frame)
    # -----------------------------------------------------------------------
    section("TASK 4 - Closing Line Audit")
    # Use pre-normalized all_sched; spread_line/total_line kept as-is (float64)
    raw_sched = nfl.import_schedules(years=SEASONS)  # re-fetch un-normalized for audit
    if "game_type" in raw_sched.columns:
        reg = raw_sched[raw_sched["game_type"] == "REG"].copy()
    elif "season_type" in raw_sched.columns:
        reg = raw_sched[raw_sched["season_type"] == "REG"].copy()
    else:
        reg = raw_sched.copy()

    total_reg = len(reg)
    spread_present = "spread_line" in reg.columns
    spread_nulls = int(reg["spread_line"].isna().sum()) if spread_present else total_reg
    null_pct = 100 * spread_nulls / total_reg if total_reg > 0 else 100

    print(f"\n  spread_line present : {spread_present}")
    print(f"  total_line present  : {'total_line' in reg.columns}")
    print(f"  REG games 2015-{CURRENT_SEASON}: {total_reg}")
    print(f"  spread_line nulls   : {spread_nulls} ({null_pct:.1f}%)\n")
    print(f"  {'Season':<8} {'Nulls':>6} {'Games':>6} {'Null%':>7}")
    print("  " + "-" * 32)
    for s in sorted(reg[season_col].unique()):
        sdf = reg[reg[season_col] == s]
        n = len(sdf)
        sn = int(sdf["spread_line"].isna().sum()) if spread_present else n
        print(f"  {s:<8} {sn:>6} {n:>6} {100*sn/n:>6.1f}%")

    if null_pct <= 5.0:
        print(f"\n  RESULT: {null_pct:.1f}% null rate <= 5% - OPTION 1 PASSES")
        print("  Source: nflverse spread_line/total_line (closing lines, home perspective)")
        print("  No separate raw_lines table needed.\n")
    else:
        print(f"\n  RESULT: {null_pct:.1f}% null rate > 5% - OPTION 1 FAILS. Stopping.\n")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # TASK 1: raw_nflfastr.pbp  (slow ~20 min)
    # -----------------------------------------------------------------------
    section("TASK 1 - raw_nflfastr.pbp  (slow step, ~20 min for all seasons)")
    if pbp_start <= 2015:
        drop(client, "raw_nflfastr.pbp")
    ensure_table_with_schema(
        client, "raw_nflfastr.pbp",
        [bigquery.SchemaField("season",  "INTEGER"),
         bigquery.SchemaField("game_id", "STRING"),
         bigquery.SchemaField("posteam", "STRING")],
        partition_field="season",
        clustering_fields=["game_id", "posteam"],
    )
    pbp_totals = {}
    for s in SEASONS:
        if s < pbp_start:
            log.info(f"  PBP {s} - skipped (--pbp-start={pbp_start})")
            pbp_totals[s] = 0
            continue
        log.info(f"  PBP {s} - fetching...")
        df = adapter.fetch_pbp(s)
        df = normalize_for_raw(df, keep_int=["season"])
        # Coerce any columns that already exist in BQ back to their established
        # type, preventing FLOAT->STRING or INTEGER->FLOAT conflicts in later seasons
        df = coerce_to_bq_schema(client, df, f"{PROJECT}.raw_nflfastr.pbp")
        bq_load(client, df, f"{PROJECT}.raw_nflfastr.pbp${s}")
        pbp_totals[s] = len(df)
        log.info(f"  OK raw_nflfastr.pbp${s} - {len(df):,} rows")

    # -----------------------------------------------------------------------
    # TASK 3: raw_nflfastr.rosters
    # -----------------------------------------------------------------------
    section("TASK 3 - raw_nflfastr.rosters")
    drop(client, "raw_nflfastr.rosters")
    ensure_table_with_schema(
        client, "raw_nflfastr.rosters",
        [bigquery.SchemaField("season", "INTEGER"),
         bigquery.SchemaField("team",   "STRING"),
         bigquery.SchemaField("week",   "INTEGER")],
        partition_field="season",
    )
    log.info("Fetching all roster seasons at once...")
    all_rosters = nfl.import_weekly_rosters(years=SEASONS)
    all_rosters = normalize_for_raw(all_rosters, keep_int=["season", "week"])

    roster_totals = {}
    roster_season_col = "season" if "season" in all_rosters.columns else "year"
    for s in SEASONS:
        df = all_rosters[all_rosters[roster_season_col] == s].copy()
        df["source"] = "nflfastR"
        df["license_tag"] = "open"
        bq_load(client, df, f"{PROJECT}.raw_nflfastr.rosters${s}")
        roster_totals[s] = len(df)
        log.info(f"  OK raw_nflfastr.rosters${s} - {len(df):,} rows")

    # -----------------------------------------------------------------------
    # TASK 5: curated.games
    # -----------------------------------------------------------------------
    section("TASK 5 - curated.games")

    GAMES_SCHEMA = [
        bigquery.SchemaField("game_id",          "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("season",            "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("week",              "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("game_date",         "DATE",    mode="REQUIRED"),
        bigquery.SchemaField("home_team",         "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("away_team",         "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("home_score",        "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("away_score",        "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("home_spread_close", "FLOAT",   mode="NULLABLE"),
        bigquery.SchemaField("total_close",       "FLOAT",   mode="NULLABLE"),
        bigquery.SchemaField("home_covered",      "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("season_type",       "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("roof",              "STRING",  mode="NULLABLE"),
        bigquery.SchemaField("surface",           "STRING",  mode="NULLABLE"),
        bigquery.SchemaField("div_game",          "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("stadium",           "STRING",  mode="NULLABLE"),
        bigquery.SchemaField("temp",              "FLOAT",   mode="NULLABLE"),
        bigquery.SchemaField("wind",              "FLOAT",   mode="NULLABLE"),
    ]
    drop(client, "curated.games")
    ensure_table_with_schema(
        client, "curated.games", GAMES_SCHEMA,
        partition_field="season",
        clustering_fields=["home_team", "away_team"],
    )
    games_totals = {}
    for s in SEASONS:
        q = f"SELECT * FROM `{PROJECT}.raw_nflfastr.schedules` WHERE season = {s}"
        df = client.query(q).to_dataframe()

        # Detect and normalize game_type / season_type column
        if "game_type" in df.columns:
            df = df[df["game_type"] == "REG"].copy()
            df.rename(columns={"game_type": "season_type"}, inplace=True)
        elif "season_type" in df.columns:
            df = df[df["season_type"] == "REG"].copy()

        df.rename(columns={"gameday": "game_date"}, errors="ignore", inplace=True)
        df.rename(columns={"spread_line": "home_spread_close"}, errors="ignore", inplace=True)
        df.rename(columns={"total_line": "total_close"}, errors="ignore", inplace=True)

        # Derive home_covered: True/False/None (None on push or missing data)
        if "home_spread_close" in df.columns:
            hs = pd.to_numeric(df.get("home_score"), errors="coerce")
            aw = pd.to_numeric(df.get("away_score"), errors="coerce")
            sp = pd.to_numeric(df["home_spread_close"], errors="coerce")
            margin = hs - aw
            # nflverse spread_line sign convention: POSITIVE = home favored.
            # Home covers if margin > spread_line (e.g. spread=+7, home must win by >7).
            # Do NOT negate sp here — that was the original bug (PR-001).
            required = sp
            # Use df.index so boolean mask aligns after REG filter slice
            covered = pd.Series([None] * len(df), dtype=object, index=df.index)
            valid = margin.notna() & required.notna()
            covered[valid & (margin > required)] = True
            covered[valid & (margin < required)] = False
            df["home_covered"] = covered
        else:
            df["home_covered"] = None

        df["season_type"] = "REG"

        if "game_date" in df.columns:
            df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce").dt.date

        # Coerce numeric fields that raw layer stored as string
        for col in ["home_score", "away_score", "home_spread_close", "total_close", "temp", "wind"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce")

        # div_game: convert "True"/"False" strings back to bool
        if "div_game" in df.columns:
            df["div_game"] = df["div_game"].map(
                {"True": True, "False": False, "1": True, "0": False, "": None, True: True, False: False}
            )

        cols = [f.name for f in GAMES_SCHEMA]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols].copy()

        bq_load(client, df, f"{PROJECT}.curated.games${s}", schema=GAMES_SCHEMA)
        games_totals[s] = len(df)
        log.info(f"  OK curated.games${s} - {len(df):,} REG games")

    # -----------------------------------------------------------------------
    # TASK 6: curated.plays
    # -----------------------------------------------------------------------
    section("TASK 6 - curated.plays")

    PLAYS_SCHEMA = [
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
    BOOL_COLS = ["qb_hit", "sack", "touchdown", "interception", "fumble", "fumble_lost", "penalty"]
    PLAYS_COLS = [f.name for f in PLAYS_SCHEMA]

    drop(client, "curated.plays")
    ensure_table_with_schema(
        client, "curated.plays", PLAYS_SCHEMA,
        partition_field="season",
        clustering_fields=["game_id", "posteam"],
    )
    plays_totals = {}
    for s in SEASONS:
        q = f"""
            SELECT
                p.play_id, p.game_id, p.season, p.week,
                p.posteam, p.defteam, p.play_type,
                p.down, p.ydstogo, p.yardline_100, p.yards_gained,
                p.epa, p.wpa,
                p.qb_hit, p.sack, p.touchdown, p.interception,
                p.fumble, p.fumble_lost,
                p.cpoe, p.air_yards, p.yards_after_catch,
                p.score_differential, p.game_half,
                p.passer_player_id, p.passer_player_name,
                p.rusher_player_id, p.rusher_player_name,
                p.receiver_player_id, p.receiver_player_name,
                p.penalty, p.penalty_type, p.penalty_team
            FROM `{PROJECT}.raw_nflfastr.pbp` p
            INNER JOIN `{PROJECT}.curated.games` g ON p.game_id = g.game_id
            WHERE p.season = {s}
        """
        df = client.query(q).to_dataframe()

        # Boolean cols: default False (not null) per spec
        for c in BOOL_COLS:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(bool)
            else:
                df[c] = False

        df["play_type"] = df["play_type"].fillna("no_play")

        # Ensure all schema columns present
        for c in PLAYS_COLS:
            if c not in df.columns:
                df[c] = None
        df = df[PLAYS_COLS].copy()

        bq_load(client, df, f"{PROJECT}.curated.plays${s}", schema=PLAYS_SCHEMA)
        plays_totals[s] = len(df)
        log.info(f"  OK curated.plays${s} - {len(df):,} plays")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    section("PIPELINE COMPLETE")
    elapsed = round(time.time() - t0)
    print(f"\n  Total runtime: {elapsed}s\n")
    print(f"  {'Season':<8} {'Sched':>7} {'PBP':>8} {'Rosters':>9} {'Games':>7} {'Plays':>8}")
    print("  " + "-" * 52)
    for s in SEASONS:
        print(f"  {s:<8} "
              f"{sched_totals.get(s,0):>7,} "
              f"{pbp_totals.get(s,0):>8,} "
              f"{roster_totals.get(s,0):>9,} "
              f"{games_totals.get(s,0):>7,} "
              f"{plays_totals.get(s,0):>8,}")
    print(f"\n  Log: pipeline.log")
    print(f"  Next: run validate_and_report.py\n")


if __name__ == "__main__":
    main()

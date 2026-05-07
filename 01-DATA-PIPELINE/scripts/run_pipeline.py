"""
Master pipeline runner — Phase 1.
Runs all tasks in sequence within a single Python process.

Usage:
    python scripts/run_pipeline.py [--start-at STEP]

Steps:
    1  ingest_schedules
    2  audit_closing_lines  (prints report; continues automatically)
    3  ingest_pbp
    4  ingest_rosters
    5  build_curated_games
    6  build_curated_plays
    7  validate_and_report
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent.parent / "pipeline.log", encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)

CURRENT_SEASON = datetime.now().year - (1 if datetime.now().month < 7 else 0)
SEASONS = list(range(2015, CURRENT_SEASON + 1))

PROJECT = "nfl-model-471509"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def drop_table_if_exists(client, table_ref: str):
    """Drop a BQ table so it can be recreated with a clean schema."""
    from google.cloud.exceptions import NotFound
    full = f"{PROJECT}.{table_ref}"
    try:
        client.delete_table(full)
        logger.info(f"Dropped existing table: {full}")
    except NotFound:
        logger.info(f"Table {full} does not exist — nothing to drop")


def step(name: str, fn, *args, **kwargs):
    logger.info(f"\n{'='*60}")
    logger.info(f"STEP: {name}")
    logger.info(f"{'='*60}")
    t0 = time.time()
    result = fn(*args, **kwargs)
    elapsed = round(time.time() - t0, 1)
    logger.info(f"STEP COMPLETE: {name} ({elapsed}s)")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Step implementations
# ──────────────────────────────────────────────────────────────────────────────

def run_ingest_schedules(client, adapter):
    from scripts.ingest_schedules import ingest_season, TABLE, SCHEMA
    from scripts.bq_utils import ensure_datasets, ensure_table_with_schema

    ensure_datasets(client, ["raw_nflfastr"])
    drop_table_if_exists(client, TABLE)
    ensure_table_with_schema(client, TABLE, SCHEMA, partition_field="season")

    results = []
    for season in SEASONS:
        r = ingest_season(client, adapter, season)
        results.append(r)
    _print_summary("Schedules Ingest", results)
    return results


def run_audit_closing_lines():
    """Inline audit — prints findings to stdout and returns the null rate."""
    import nfl_data_py as nfl
    import pandas as pd

    logger.info("Fetching schedules for closing line audit...")
    df = nfl.import_schedules(years=SEASONS)

    # Detect REG filter column
    if "game_type" in df.columns:
        reg = df[df["game_type"] == "REG"].copy()
    elif "season_type" in df.columns:
        reg = df[df["season_type"] == "REG"].copy()
    else:
        reg = df.copy()

    season_col = "season" if "season" in reg.columns else "year"
    total = len(reg)
    spread_nulls = reg["spread_line"].isna().sum() if "spread_line" in reg.columns else total
    null_pct = 100 * spread_nulls / total if total > 0 else 100

    print("\n" + "="*60)
    print("TASK 4 — CLOSING LINE AUDIT")
    print("="*60)
    print(f"  spread_line present:  {'YES' if 'spread_line' in reg.columns else 'NO'}")
    print(f"  total_line present:   {'YES' if 'total_line' in reg.columns else 'NO'}")
    print(f"  REG games 2015-{CURRENT_SEASON}: {total}")
    print(f"  spread_line nulls:    {spread_nulls} ({null_pct:.1f}%)")
    print()

    print(f"  {'Season':<8}{'Spread Nulls':>14}{'Total':>8}{'Null %':>9}")
    print("  " + "-"*42)
    for s in sorted(reg[season_col].unique()):
        sdf = reg[reg[season_col] == s]
        n = len(sdf)
        sn = sdf["spread_line"].isna().sum() if "spread_line" in sdf.columns else n
        pct = 100 * sn / n if n > 0 else 100
        print(f"  {s:<8}{sn:>14}{n:>8}{pct:>8.1f}%")

    print()
    if null_pct <= 5.0:
        decision = "OPTION 1 — Use nflverse schedules spread_line/total_line directly"
        print(f"  RESULT: {null_pct:.1f}% null rate ≤ 5% → {decision}")
    else:
        decision = "OPTION 1 FAILS — investigate alternative closing line source"
        print(f"  RESULT: {null_pct:.1f}% null rate > 5% → {decision}")
    print("="*60 + "\n")

    return null_pct


def run_ingest_pbp(client, adapter):
    from scripts.ingest_pbp import ingest_season, TABLE, SCHEMA
    from scripts.bq_utils import ensure_datasets, ensure_table_with_schema
    from google.cloud import bigquery

    ensure_datasets(client, ["raw_nflfastr"])
    drop_table_if_exists(client, TABLE)
    ensure_table_with_schema(
        client, TABLE, SCHEMA,
        partition_field="season",
        clustering_fields=["game_id", "posteam"],
    )

    results = []
    for season in SEASONS:
        r = ingest_season(client, adapter, season)
        results.append(r)
    _print_summary("PBP Ingest", results)
    return results


def run_ingest_rosters(client, adapter):
    from scripts.ingest_rosters import ingest_season, TABLE, SCHEMA
    from scripts.bq_utils import ensure_datasets, ensure_table_with_schema

    ensure_datasets(client, ["raw_nflfastr"])
    drop_table_if_exists(client, TABLE)
    ensure_table_with_schema(client, TABLE, SCHEMA, partition_field="season")

    results = []
    for season in SEASONS:
        r = ingest_season(client, adapter, season)
        results.append(r)
    _print_summary("Rosters Ingest", results)
    return results


def run_build_curated_games(client):
    from scripts.build_curated_games import build_season, CURATED_TABLE, SCHEMA
    from scripts.bq_utils import ensure_datasets, ensure_table_with_schema

    ensure_datasets(client, ["curated"])
    drop_table_if_exists(client, CURATED_TABLE)
    ensure_table_with_schema(
        client, CURATED_TABLE, SCHEMA,
        partition_field="season",
        clustering_fields=["home_team", "away_team"],
    )

    results = []
    for season in SEASONS:
        r = build_season(client, season)
        results.append(r)
    _print_summary("curated.games", results)
    return results


def run_build_curated_plays(client):
    from scripts.build_curated_plays import build_season, CURATED_TABLE, SCHEMA
    from scripts.bq_utils import ensure_datasets, ensure_table_with_schema

    ensure_datasets(client, ["curated"])
    drop_table_if_exists(client, CURATED_TABLE)
    ensure_table_with_schema(
        client, CURATED_TABLE, SCHEMA,
        partition_field="season",
        clustering_fields=["game_id", "posteam"],
    )

    results = []
    for season in SEASONS:
        r = build_season(client, season)
        results.append(r)
    _print_summary("curated.plays", results)
    return results


def run_validate(client):
    import scripts.validate_and_report as vr
    vr.client = client  # inject already-open client
    vr.main()


def _print_summary(label: str, results: list):
    print(f"\n  === {label} Summary ===")
    total = 0
    for r in results:
        rows = r.get("rows", 0)
        total += rows
        print(f"    {r['season']}: {rows:>8,} rows  [{r['status']}]")
    print(f"    TOTAL: {total:,} rows\n")
    failed = [r for r in results if r["status"] not in ("OK", "EMPTY")]
    if failed:
        seasons = [r["season"] for r in failed]
        logger.error(f"{label}: {len(failed)} season(s) failed: {seasons}")
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start-at", type=int, default=1,
        help="Resume from step N (1=schedules, 2=audit, 3=pbp, 4=rosters, 5=games, 6=plays, 7=validate)"
    )
    args = parser.parse_args()
    start = args.start_at

    from scripts.bq_utils import get_client
    from adapters.nflfastr import NflfastrAdapter

    client = get_client()
    adapter = NflfastrAdapter()

    t_total = time.time()

    if start <= 1:
        step("1/7 — Ingest raw schedules", run_ingest_schedules, client, adapter)

    if start <= 2:
        null_pct = step("2/7 — Audit closing lines", run_audit_closing_lines)
        if null_pct > 5.0:
            logger.error("Closing line null rate > 5%. Stopping — review source before curated layer.")
            sys.exit(1)

    if start <= 3:
        step("3/7 — Ingest raw PBP", run_ingest_pbp, client, adapter)

    if start <= 4:
        step("4/7 — Ingest raw rosters", run_ingest_rosters, client, adapter)

    if start <= 5:
        step("5/7 — Build curated.games", run_build_curated_games, client)

    if start <= 6:
        step("6/7 — Build curated.plays", run_build_curated_plays, client)

    if start <= 7:
        step("7/7 — Validate and report", run_validate, client)

    elapsed = round(time.time() - t_total, 0)
    logger.info(f"\nPipeline complete in {elapsed}s. See VALIDATION_REPORT.md for results.")


if __name__ == "__main__":
    main()

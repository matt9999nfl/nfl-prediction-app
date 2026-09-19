#!/usr/bin/env python3
"""
Append-only daily capture of nflverse injury reports and depth charts.

Why this exists
----------------
`raw_ol_sources.nflverse_ol_injuries` and `.nflverse_ol_depth_charts` (loaded by
`new_sources_staging/load_to_bigquery.py`) each hold exactly one archived row per
player-week -- the week's FINAL report. There is no Wednesday/Thursday/Friday
practice-status progression in that archive and there never will be one; the
only way to ever have it is to capture it as it happens, starting now. This
script is that clock. It builds no feature and touches no model (B1-3c).

Design point 1 -- why this is not inside run_pipeline.py
----------------------------------------------------------
`run_pipeline.py` drops and rebuilds its landing tables as its first act, and
spent a week crash-looping on one missing IAM grant (QUESTIONS.md, 2026-09-18).
A capture job whose only job is to never miss a day must not share fate with
that. This script has its own Cloud Run job and its own Cloud Scheduler entry
(05-DEVOPS/infra/terraform/jobs.tf, scheduler.tf) and can run whether or not
the main pipeline is healthy that day.

Design point 2 -- cadence
--------------------------
nflverse's injuries feed refreshes once daily. This job is scheduled for
08:00 UTC, one hour after that refresh, so every day's capture sees that day's
data rather than racing it. See `05-DEVOPS/infra/terraform/scheduler.tf` for
the schedule and PROMPT-CAPTURE-INJURY-SNAPSHOTS.md for what daily capture does
and does not buy over the weekly cadence the archive already has.

Traps in this data (see PLAN-BUCKET1-DATA-COVERAGE.md, point-in-time
verification), all confirmed against a live fetch, not just the archive:
  - `report_status` uses the LITERAL STRING "None" for roughly half of all
    rows, not NULL. An `IS NULL` check silently misses them (same class of
    defect as INC-001). This code never filters on nullness of that column --
    it is compared and stored verbatim, "None" included.
  - `date_modified` (nflverse's own timestamp) can be null or simply absent
    depending on season; this script never relies on it for the observation
    clock. Every row here also carries `captured_at`, which is this job's own
    clock and is never null.
  - Depth charts are not unique per player-week: a player can appear at more
    than one `depth_position` in the same week (up to 8 rows for one
    player-week in the archive). `depth_position` is part of the identity key
    here, not a compared column, so two simultaneous rows for the same player
    are tracked independently rather than colliding or overwriting each other.

Failure handling
-----------------
Three levels exist and only one is correct (the B1-2a lesson, QUESTIONS.md
2026-09-18): crashing this job is too much (an unhandled exception here would
only cost a day of capture, not corrupt anything, but Cloud Run Jobs retries a
failed execution automatically -- no reason to spend retries on a feed hiccup
that tomorrow's run will fix); logging an error alone is demonstrably too
little (nine days of silent snapshot_lines.py failures went unnoticed the same
way). So `main()` never raises: each source is captured independently, a
failure is logged loudly and returned in the result, and the process always
exits 0. The thing that must not be silent -- a capture that has stopped
running -- is caught by `roster_snapshot_freshness.py`'s check inside
`validate_and_report.py`, which fails the pipeline's own validation report
visibly if either table goes stale. That is the one correct level.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import nfl_data_py as nfl
import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)


def current_season() -> int:
    """
    The NFL season we are currently in. Seasons are named for the year they
    start and run into the following February, so before July we are still
    in the previous year's season.

    Duplicated from adapters/nflfastr.py rather than imported: that import
    only resolves when the process cwd is 01-DATA-PIPELINE/ (true for the
    deployed job, WORKDIR /app in Dockerfile.job), but breaks test collection
    when pytest is invoked from the repo root, which is how every other test
    in this folder is documented to run.
    """
    now = datetime.now()
    return now.year - (1 if now.month < 7 else 0)

PROJECT = "nfl-model-471509"
DATASET = "raw_roster_snapshots"

INJURY_TABLE = "injury_report_snapshots"
DEPTH_CHART_TABLE = "depth_chart_snapshots"
INJURY_TABLE_REF = f"{PROJECT}.{DATASET}.{INJURY_TABLE}"
DEPTH_CHART_TABLE_REF = f"{PROJECT}.{DATASET}.{DEPTH_CHART_TABLE}"

# Identity key: two rows with the same key values are the same observed thing.
# depth_position is part of the KEY, not a compared column, precisely because
# depth charts are not unique per player-week -- see the module docstring.
INJURY_KEY = ["season", "week", "team", "gsis_id"]
DEPTH_CHART_KEY = ["season", "week", "team", "gsis_id", "depth_position"]

# Columns whose change (for an already-seen key) triggers a new captured row.
INJURY_COMPARE_COLS = [
    "report_primary_injury",
    "report_secondary_injury",
    "report_status",
    "practice_primary_injury",
    "practice_secondary_injury",
    "practice_status",
]
DEPTH_CHART_COMPARE_COLS = ["depth_team", "formation", "jersey_number"]

INJURY_SCHEMA = [
    bigquery.SchemaField("season", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("week", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("game_type", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("team", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("gsis_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("full_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("position", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("report_primary_injury", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("report_secondary_injury", "STRING", mode="NULLABLE"),
    # NULLABLE, but "no report" is the literal string "None" for ~half of all
    # rows, not NULL. See the module docstring -- never IS NULL this column.
    bigquery.SchemaField("report_status", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("practice_primary_injury", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("practice_secondary_injury", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("practice_status", "STRING", mode="NULLABLE"),
    # nflverse's own timestamp. Informational only -- can be null or stale by
    # season; `captured_at` below is the observation clock this stage exists
    # to create and is never null.
    bigquery.SchemaField("date_modified", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("captured_at", "TIMESTAMP", mode="REQUIRED"),
]

DEPTH_CHART_SCHEMA = [
    bigquery.SchemaField("season", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("week", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("game_type", "STRING", mode="NULLABLE"),
    # Source column is `club_code`, not `team` -- nfl_data_py's live
    # import_depth_charts() has no `team` column at all (confirmed 2026-09-19
    # against a live fetch; the archived parquet's `team`/`dt`/`espn_id` etc.
    # columns come from some other enrichment, not this function). Renamed to
    # `team` on the way in so this table matches every other table's naming.
    bigquery.SchemaField("team", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("gsis_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("full_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("position", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("depth_position", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("depth_team", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("formation", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("jersey_number", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("captured_at", "TIMESTAMP", mode="REQUIRED"),
]


def ensure_tables(client: bigquery.Client) -> None:
    """Create the dataset and both tables if absent. Never drops -- like
    line_snapshots, this is the only record of what a report said at a point
    in time; it cannot be rebuilt from any source we have."""
    dataset_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)

    for table_ref, schema in (
        (INJURY_TABLE_REF, INJURY_SCHEMA),
        (DEPTH_CHART_TABLE_REF, DEPTH_CHART_SCHEMA),
    ):
        table = bigquery.Table(table_ref, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(field="captured_at")
        table.clustering_fields = ["season", "team"]
        client.create_table(table, exists_ok=True)


# ---------------------------------------------------------------------------
# Fetch + normalize (network + pandas only, no BigQuery)
# ---------------------------------------------------------------------------


def fetch_injuries(seasons: list[int]) -> pd.DataFrame:
    df = nfl.import_injuries(seasons)
    keep = [
        "season", "week", "game_type", "team", "gsis_id", "full_name", "position",
        "report_primary_injury", "report_secondary_injury", "report_status",
        "practice_primary_injury", "practice_secondary_injury", "practice_status",
        "date_modified",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    df = df.dropna(subset=["gsis_id", "team"])
    df["season"] = df["season"].astype("int64")
    df["week"] = df["week"].astype("int64")
    return df.reset_index(drop=True)


def fetch_depth_charts(seasons: list[int]) -> pd.DataFrame:
    df = nfl.import_depth_charts(seasons)
    df = df.rename(columns={"club_code": "team"})
    keep = [
        "season", "week", "game_type", "team", "gsis_id", "full_name", "position",
        "depth_position", "depth_team", "formation", "jersey_number",
    ]
    df = df[[c for c in keep if c in df.columns]].copy()
    # week arrives as float64 from this endpoint (unlike injuries, which is
    # already int); drop rows with no week before casting rather than let a
    # missing value become 0 or crash the cast.
    df = df.dropna(subset=["week", "gsis_id", "team", "depth_position"])
    df["season"] = df["season"].astype("int64")
    df["week"] = df["week"].astype("int64")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Diff against what is already stored -- pure, no BigQuery, fully unit-testable
# ---------------------------------------------------------------------------

# Any value not expected to occur in real nflverse data, used to make two
# nulls compare equal without ever colliding with a genuine value -- including
# the genuine value "None" (see module docstring), which must NOT be treated
# as equivalent to a null.
_NULL_SENTINEL = "\x00__CAPTURE_NULL__\x00"


def _series_differs(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise: True where two values are a real change.

    fillna() only touches actual pandas/NumPy nulls (NaN, NaT, None) -- the
    literal string "None" that nflverse uses for "no report" is a normal
    string value to pandas and passes through untouched, so it is compared
    like any other value rather than being coerced into "no change".
    """
    return a.fillna(_NULL_SENTINEL).astype(str) != b.fillna(_NULL_SENTINEL).astype(str)


def rows_to_capture(
    fetched: pd.DataFrame, latest: pd.DataFrame, key_cols: list[str], compare_cols: list[str],
) -> pd.DataFrame:
    """
    Return the rows of `fetched` that are new (key not present in `latest`)
    or have at least one `compare_cols` value that differs from `latest`'s
    row for that key. Everything else is an unchanged re-observation and is
    dropped, which is what keeps this an append-only change-log instead of a
    full copy of the source on every run.
    """
    if latest.empty:
        return fetched.copy()

    merged = fetched.merge(
        latest[key_cols + compare_cols],
        on=key_cols,
        how="left",
        suffixes=("", "_prev"),
        indicator=True,
    )
    is_new = merged["_merge"] == "left_only"
    changed = pd.Series(False, index=merged.index)
    for col in compare_cols:
        changed = changed | _series_differs(merged[col], merged[f"{col}_prev"])

    keep_mask = (is_new | changed).to_numpy()
    return fetched.loc[keep_mask].reset_index(drop=True).copy()


def _latest_snapshot(
    client: bigquery.Client, table_ref: str, key_cols: list[str], compare_cols: list[str],
) -> pd.DataFrame:
    """Most recent captured row per key, read back from BigQuery."""
    cols_sql = ", ".join(key_cols + compare_cols)
    key_sql = ", ".join(key_cols)
    query = f"""
        SELECT {cols_sql} FROM (
          SELECT {cols_sql},
                 ROW_NUMBER() OVER (PARTITION BY {key_sql} ORDER BY captured_at DESC) AS rn
          FROM `{table_ref}`
        )
        WHERE rn = 1
    """
    return client.query(query).to_dataframe()


# ---------------------------------------------------------------------------
# Per-source capture
# ---------------------------------------------------------------------------


def snapshot_injuries(client: bigquery.Client, seasons: list[int] | None = None) -> dict:
    ensure_tables(client)
    seasons = seasons or [current_season()]
    captured_at = datetime.now(timezone.utc)

    fetched = fetch_injuries(seasons)
    latest = _latest_snapshot(client, INJURY_TABLE_REF, INJURY_KEY, INJURY_COMPARE_COLS)
    new_rows = rows_to_capture(fetched, latest, INJURY_KEY, INJURY_COMPARE_COLS)

    if new_rows.empty:
        logger.info("  %s: no changes", INJURY_TABLE)
        return {"table": INJURY_TABLE, "status": "OK", "inserted": 0}

    new_rows["captured_at"] = captured_at
    job_config = bigquery.LoadJobConfig(
        schema=INJURY_SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_dataframe(new_rows, INJURY_TABLE_REF, job_config=job_config)
    job.result()
    logger.info("  %s: inserted %d row(s)", INJURY_TABLE, len(new_rows))
    return {"table": INJURY_TABLE, "status": "OK", "inserted": int(len(new_rows))}


def snapshot_depth_charts(client: bigquery.Client, seasons: list[int] | None = None) -> dict:
    ensure_tables(client)
    seasons = seasons or [current_season()]
    captured_at = datetime.now(timezone.utc)

    fetched = fetch_depth_charts(seasons)
    latest = _latest_snapshot(client, DEPTH_CHART_TABLE_REF, DEPTH_CHART_KEY, DEPTH_CHART_COMPARE_COLS)
    new_rows = rows_to_capture(fetched, latest, DEPTH_CHART_KEY, DEPTH_CHART_COMPARE_COLS)

    if new_rows.empty:
        logger.info("  %s: no changes", DEPTH_CHART_TABLE)
        return {"table": DEPTH_CHART_TABLE, "status": "OK", "inserted": 0}

    new_rows["captured_at"] = captured_at
    job_config = bigquery.LoadJobConfig(
        schema=DEPTH_CHART_SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_dataframe(new_rows, DEPTH_CHART_TABLE_REF, job_config=job_config)
    job.result()
    logger.info("  %s: inserted %d row(s)", DEPTH_CHART_TABLE, len(new_rows))
    return {"table": DEPTH_CHART_TABLE, "status": "OK", "inserted": int(len(new_rows))}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = bigquery.Client(project=PROJECT)

    results = []
    for fn in (snapshot_injuries, snapshot_depth_charts):
        try:
            results.append(fn(client))
        except Exception as exc:  # noqa: BLE001 -- see "Failure handling" above
            logger.error("  %s FAILED: %s", fn.__name__, exc)
            results.append({"table": fn.__name__, "status": "FAILED", "error": str(exc), "inserted": 0})

    print(results)
    return 0  # always -- see module docstring, "Failure handling"


if __name__ == "__main__":
    raise SystemExit(main())

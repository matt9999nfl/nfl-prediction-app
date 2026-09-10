#!/usr/bin/env python3
"""
Append-only capture of betting lines from nflverse schedules.

Why this exists
---------------
`raw_nflfastr.schedules` is dropped and rebuilt on every pipeline run, and
`curated.games` holds exactly one spread per game in a column that is
overwritten each time.  There is nowhere in the current schema to record that a
line moved, so opening/closing spread and closing-line value are not questions
the platform can answer — regardless of data source.

This writes a change-log instead: one row each time a game's market data differs
from the last row we stored for it.  Nothing is ever updated or deleted, so the
first row for a game is the first line we observed and the last row is the last
line we observed.

An honest note on "opening"
---------------------------
nflverse publishes a single `spread_line` field and NO opening-line field.  So
"opening" here means *the first value this pipeline captured*, not the true
market open.  Books post lines on Sunday evening; the earliest this pipeline
looks is Tuesday 11:00 UTC.  The derived column is therefore named
`home_spread_first_seen`, not `home_spread_open`, because a column that claims
to be an opening line and is not is exactly the kind of quietly-wrong field this
codebase has been bitten by (see INC-001, and `home_spread_close` which holds a
LIVE value for any game that has not kicked off yet).

Sign convention, from the nflverse data dictionary, verified 2026-09-09:
    spread_line — "A positive number means the home team was favored by that
    many points, a negative number means the away team was favored."
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.cloud import bigquery

logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
DATASET = "raw_lines"
TABLE = f"{PROJECT}.{DATASET}.line_snapshots"
SCHEDULES_TABLE = f"{PROJECT}.raw_nflfastr.schedules"

# Market fields nflverse publishes. The pipeline previously carried only
# spread_line and total_line into curated.games; the rest were available and
# unused. Moneylines in particular give the market's own implied win
# probability, which is the honest baseline for any model to be measured against.
MARKET_FIELDS = [
    "spread_line",
    "total_line",
    "home_moneyline",
    "away_moneyline",
    "home_spread_odds",
    "away_spread_odds",
    "over_odds",
    "under_odds",
]

# Target BigQuery type per market field. Kept beside MARKET_FIELDS so the cast
# and the table schema cannot drift apart.
FIELD_TYPES = {
    "spread_line": "FLOAT64",
    "total_line": "FLOAT64",
    "home_moneyline": "INT64",
    "away_moneyline": "INT64",
    "home_spread_odds": "INT64",
    "away_spread_odds": "INT64",
    "over_odds": "INT64",
    "under_odds": "INT64",
}

SCHEMA = [
    bigquery.SchemaField("game_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("season", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("week", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("home_team", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("away_team", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("captured_at", "TIMESTAMP", mode="REQUIRED"),
    # True when the game already had a result at capture time. The last row with
    # game_completed = false is the closest thing to a closing line; rows after
    # kickoff are the settled number.
    bigquery.SchemaField("game_completed", "BOOLEAN", mode="NULLABLE"),
    bigquery.SchemaField("spread_line", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("total_line", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("home_moneyline", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("away_moneyline", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("home_spread_odds", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("away_spread_odds", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("over_odds", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("under_odds", "INTEGER", mode="NULLABLE"),
]


def ensure_table(client: bigquery.Client) -> None:
    """Create the dataset and table if absent. Never drops — this table is the
    only record of what a line was at a point in time; rebuilding it is not
    possible from any source we have."""
    dataset_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)

    table = bigquery.Table(TABLE, schema=SCHEMA)
    table.time_partitioning = bigquery.TimePartitioning(field="captured_at")
    table.clustering_fields = ["season", "game_id"]
    client.create_table(table, exists_ok=True)


def _available_market_columns(client: bigquery.Client) -> list[str]:
    """Only select market columns the schedules table actually has.

    nflverse has added odds fields over time and the ingest uses schema
    autodetect, so which columns exist varies by what has been loaded. Selecting
    a missing column fails the whole run; checking first degrades to whatever is
    present.
    """
    table = client.get_table(SCHEDULES_TABLE)
    present = {f.name for f in table.schema}
    available = [c for c in MARKET_FIELDS if c in present]
    missing = [c for c in MARKET_FIELDS if c not in present]
    if missing:
        logger.warning("  schedules table has no %s — those stay null", ", ".join(missing))
    return available


def snapshot(client: bigquery.Client, seasons: list[int] | None = None) -> dict:
    """
    Append a row for every game whose market data differs from its last snapshot.

    Unchanged games are skipped so the table stays a change-log rather than a
    4x-per-week copy of the schedule.
    """
    ensure_table(client)
    captured_at = datetime.now(timezone.utc)
    available = _available_market_columns(client)

    if "spread_line" not in available:
        logger.error("  schedules has no spread_line — nothing to snapshot")
        return {"inserted": 0, "status": "NO_SPREAD_COLUMN"}

    season_filter = ""
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = [
        bigquery.ScalarQueryParameter("captured_at", "TIMESTAMP", captured_at),
    ]
    if seasons:
        season_filter = "WHERE s.season IN UNNEST(@seasons)"
        params.append(bigquery.ArrayQueryParameter("seasons", "INT64", seasons))

    # Every column is SAFE_CAST to its target type rather than selected raw.
    #
    # raw_nflfastr.schedules is loaded with schema autodetect from pandas, and
    # pandas represents a nullable integer column as float64 -- so `week` arrives
    # as FLOAT64 and BigQuery refuses the insert into an INT64 column. The same
    # applies to every moneyline and odds field, which are nullable ints at
    # source. Casting also means the comparison against the previous snapshot
    # compares like with like instead of 1.0 against 1.
    #
    # SAFE_CAST rather than CAST: an unparseable value yields NULL for that one
    # field instead of failing the whole run mid-season.
    def _cast(col: str) -> str:
        target = FIELD_TYPES[col]
        return f"SAFE_CAST(s.{col} AS {target}) AS {col}"

    select_cols = ",\n              ".join(_cast(c) for c in available)
    null_cols = ",\n              ".join(
        f"CAST(NULL AS {FIELD_TYPES[c]}) AS {c}"
        for c in MARKET_FIELDS if c not in available
    )
    all_cols = select_cols + ((",\n              " + null_cols) if null_cols else "")

    # Compare against the most recent snapshot per game. IS DISTINCT FROM
    # treats NULL as a value, so a line appearing (null -> 3.5) or being pulled
    # (3.5 -> null) both register as changes rather than being silently skipped.
    compare = " OR ".join(
        f"latest.{c} IS DISTINCT FROM src.{c}" for c in MARKET_FIELDS
    )

    query = f"""
        INSERT INTO `{TABLE}`
          (game_id, season, week, home_team, away_team, captured_at, game_completed,
           spread_line, total_line, home_moneyline, away_moneyline,
           home_spread_odds, away_spread_odds, over_odds, under_odds)
        WITH src AS (
          SELECT
              CAST(s.game_id AS STRING) AS game_id,
              SAFE_CAST(s.season AS INT64) AS season,
              SAFE_CAST(s.week AS INT64) AS week,
              CAST(s.home_team AS STRING) AS home_team,
              CAST(s.away_team AS STRING) AS away_team,
              (s.home_score IS NOT NULL AND s.away_score IS NOT NULL) AS game_completed,
              {all_cols}
          FROM `{SCHEDULES_TABLE}` s
          {season_filter}
        ),
        latest AS (
          SELECT * EXCEPT(rn) FROM (
            SELECT l.*, ROW_NUMBER() OVER (
                     PARTITION BY l.game_id ORDER BY l.captured_at DESC
                   ) AS rn
            FROM `{TABLE}` l
          ) WHERE rn = 1
        )
        SELECT
            src.game_id, src.season, src.week, src.home_team, src.away_team,
            @captured_at, src.game_completed,
            src.spread_line, src.total_line, src.home_moneyline, src.away_moneyline,
            src.home_spread_odds, src.away_spread_odds, src.over_odds, src.under_odds
        FROM src
        LEFT JOIN latest ON latest.game_id = src.game_id
        WHERE latest.game_id IS NULL
           OR {compare}
           OR latest.game_completed IS DISTINCT FROM src.game_completed
    """

    job = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    inserted = job.num_dml_affected_rows or 0
    logger.info("  line_snapshots: inserted %s changed row(s)", inserted)
    return {"inserted": int(inserted), "status": "OK", "captured_at": captured_at.isoformat()}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = bigquery.Client(project=PROJECT)
    result = snapshot(client)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

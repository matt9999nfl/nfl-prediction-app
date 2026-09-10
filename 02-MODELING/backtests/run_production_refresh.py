#!/usr/bin/env python3
"""
Weekly production refresh — grade last week, predict this week.

Runs as the `nfl-production-refresh` Cloud Run Job, fired by the
`nfl-production-refresh-weekly` scheduler every Tuesday at 14:00 UTC.

What this used to do, and why it did nothing
--------------------------------------------
The previous version queried `platform.experiment_configs` for experiments with
`gate_passed = true` and fired one experiment-runner execution per result. No
experiment has ever cleared its success gate, so the query returned zero rows,
the job logged "No gate-passed experiments found — nothing to refresh", exited 0,
and looked healthy. It had been doing that every Tuesday since it was created.

It also would not have helped if an experiment HAD passed: the experiment runner
runs a walk-forward backtest over completed seasons. It cannot emit a prediction
for a game that has not been played.

What it does now
----------------
1. Grades any week whose predictions are still ungraded but whose games have
   finished — so last week's picks get their result automatically.
2. Predicts the next week that has unplayed games.

Both steps are idempotent. Re-running replaces the week's predictions rather than
appending a second generation, and grading an already-graded week is a no-op.

DEC-C applies throughout: nothing here has cleared a success gate, the config is
written with `gate_passed = false`, and the frontend shows the evaluation banner
because of it. This job makes unvalidated predictions *current*; it does not make
them validated.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests.predict_upcoming import (  # noqa: E402
    PRODUCTION_EXPERIMENT_ID,
    generate_predictions,
    grade_completed,
    preflight,
    replace_week_predictions,
    upsert_production_config,
    write_run_row,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT = os.environ.get("BIGQUERY_PROJECT", "nfl-model-471509")
GAMES_TABLE = f"{PROJECT}.curated.games"
PREDS_TABLE = f"{PROJECT}.experiments.backtest_predictions"

# Optional override for a manual/backfill run, e.g. to regenerate a specific week.
FORCE_SEASON = os.environ.get("REFRESH_SEASON")
FORCE_WEEK = os.environ.get("REFRESH_WEEK")


def _scalar(client: bigquery.Client, query: str, params: list | None = None):
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    rows = list(client.query(query, job_config=job_config).result())
    return rows[0][0] if rows else None


def current_season(client: bigquery.Client) -> int | None:
    """The latest season present in curated.games."""
    return _scalar(client, f"SELECT MAX(season) FROM `{GAMES_TABLE}`")


def next_unplayed_week(client: bigquery.Client, season: int) -> int | None:
    """
    The earliest week in this season that still has games without a score.

    Uses home_score rather than home_covered: a completed game can have a null
    home_covered (a push, or a missing line), and treating those as unplayed
    would make the job predict a week that has already happened.
    """
    return _scalar(
        client,
        f"""
        SELECT MIN(week) FROM `{GAMES_TABLE}`
        WHERE season = @season
          AND season_type = 'REG'
          AND home_score IS NULL
        """,
        [bigquery.ScalarQueryParameter("season", "INT64", season)],
    )


def weeks_awaiting_grade(client: bigquery.Client, season: int) -> list[int]:
    """Weeks with predictions that have no result recorded but whose games are done."""
    query = f"""
        SELECT DISTINCT p.week
        FROM `{PREDS_TABLE}` p
        JOIN `{GAMES_TABLE}` g ON g.game_id = p.game_id
        WHERE p.experiment_id = @eid
          AND p.season = @season
          AND p.correct IS NULL
          AND g.home_covered IS NOT NULL
        ORDER BY p.week
    """
    params = [
        bigquery.ScalarQueryParameter("eid", "STRING", PRODUCTION_EXPERIMENT_ID),
        bigquery.ScalarQueryParameter("season", "INT64", season),
    ]
    rows = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    return [r["week"] for r in rows]


def main() -> int:
    logger.info("Production refresh starting — project=%s", PROJECT)
    client = bigquery.Client(project=PROJECT)

    # Fail fast and loudly on a schema mismatch, before any expensive loading.
    preflight(client)

    season = int(FORCE_SEASON) if FORCE_SEASON else current_season(client)
    if season is None:
        logger.error("curated.games is empty — cannot determine the season")
        return 1
    logger.info("Season: %s", season)

    failures: list[str] = []

    # ── 1. Grade anything that finished since the last run ────────────────────
    #
    # Deliberately before prediction: if the prediction step fails, last week's
    # results are still recorded. Losing the record of how picks actually did is
    # worse than being a week late on new ones.
    try:
        pending = weeks_awaiting_grade(client, season)
        if pending:
            logger.info("Grading completed week(s): %s", pending)
            for week in pending:
                grade_completed(client, season, week)
        else:
            logger.info("No weeks awaiting grading")
    except Exception as exc:
        logger.error("Grading FAILED: %s", exc, exc_info=True)
        failures.append(f"grading: {exc}")

    # ── 2. Predict the next unplayed week ─────────────────────────────────────
    try:
        week = int(FORCE_WEEK) if FORCE_WEEK else next_unplayed_week(client, season)
        if week is None:
            logger.info(
                "No unplayed regular-season games left in %s — nothing to predict. "
                "This is the expected state once the season ends.", season,
            )
        else:
            logger.info("Predicting %s week %s", season, week)
            preds, meta = generate_predictions(client, season, week)

            run_id = str(uuid.uuid4())
            upsert_production_config(client, meta, season, week)
            replace_week_predictions(client, preds, run_id, season, week)
            write_run_row(client, run_id, meta, season, week)

            logger.info(
                "Wrote %s predictions for %s week %s (run_id=%s)",
                len(preds), season, week, run_id,
            )
    except Exception as exc:
        logger.error("Prediction FAILED: %s", exc, exc_info=True)
        failures.append(f"prediction: {exc}")

    if failures:
        # Non-zero so the Cloud Run Job is marked failed and alerting fires.
        # A refresh that quietly half-worked is how the dashboard ends up showing
        # last week's picks as if they were this week's.
        logger.error("Production refresh finished with %d failure(s)", len(failures))
        for f in failures:
            logger.error("  - %s", f)
        return 1

    logger.info("Production refresh complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

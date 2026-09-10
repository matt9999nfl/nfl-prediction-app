"""
BigQuery queries for the GET /api/v1/predictions endpoint (production predictions).

This endpoint returns per-game predictions for a given season/week from the most
recent experiment that has cleared its success gate (gate_passed = true).

Queries:
  1. Find the production experiment (most recent gate-passed run)
  2. Fetch predictions for that run filtered by season/week
"""
import logging
from typing import Any

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


# ── Step 1: Find production experiment ─────────────────────────────────────────


def get_production_experiment(
    client: bigquery.Client,
    experiment_id_override: str | None = None,
) -> dict[str, Any] | None:
    """
    Resolve the experiment that serves production predictions.

    Selection order:

      1. ``experiment_id_override``, if given.  Honoured only when that
         experiment is gate-passed OR is the configured production experiment —
         so the endpoint cannot be pointed at an arbitrary run (the shuffled-label
         leakage test, say) by editing a query string.
      2. The most recent gate-passed experiment.  If one ever exists it wins,
         because a validated model should always outrank an unvalidated one.
      3. The configured production experiment (``PRODUCTION_EXPERIMENT_ID``),
         ungated.

    Step 3 is what makes forward predictions servable at all.  No experiment has
    cleared its success gate, so requiring gate_passed meant this endpoint could
    never return anything — the structural block DEC-C identified.  DEC-C ruled
    that gate-passing is not a prerequisite for emitting a prediction, provided
    the app never presents it as validated.  Hence the returned dict always
    carries ``gate_passed``, and the response model requires it: the UI is told
    what it is serving rather than trusted to remember.

    Returns a dict with: experiment_id, run_id, completed_at, experiment_name,
    gate_passed.  None if nothing is servable.
    """
    select_clause = """
            SELECT
              r.experiment_id,
              r.run_id,
              FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', r.completed_at) AS completed_at,
              c.name AS experiment_name,
              COALESCE(r.gate_passed, false) AS gate_passed
            FROM `{project}.experiments.backtest_runs` r
            JOIN `{project}.platform.experiment_configs` c
              ON r.experiment_id = c.experiment_id
    """.format(project=PROJECT)

    production_id = getattr(settings, "production_experiment_id", "") or ""

    if experiment_id_override:
        query = f"""
            {select_clause}
            WHERE r.experiment_id = @experiment_id
              AND (
                    (r.gate_passed = true AND c.gate_passed = true)
                 OR (@production_id != '' AND r.experiment_id = @production_id)
              )
            ORDER BY r.completed_at DESC
            LIMIT 1
        """
        params = [
            bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id_override),
            bigquery.ScalarQueryParameter("production_id", "STRING", production_id),
        ]
        rows = _run_query(client, query, params)
        return rows[0] if rows else None

    # A gate-passed experiment always wins if one exists.
    gated_query = f"""
        {select_clause}
        WHERE r.gate_passed = true
          AND c.gate_passed = true
        ORDER BY r.completed_at DESC
        LIMIT 1
    """
    rows = _run_query(client, gated_query, [])
    if rows:
        return rows[0]

    if not production_id:
        return None

    # Fall back to the designated production experiment, ungated.
    production_query = f"""
        {select_clause}
        WHERE r.experiment_id = @production_id
          AND r.status = 'complete'
        ORDER BY r.completed_at DESC
        LIMIT 1
    """
    params = [bigquery.ScalarQueryParameter("production_id", "STRING", production_id)]
    rows = _run_query(client, production_query, params)
    return rows[0] if rows else None


# ── Step 2: Fetch predictions for the production run ──────────────────────────


def get_production_predictions(
    client: bigquery.Client,
    experiment_id: str,
    season: int,
    week: int,
) -> list[dict[str, Any]]:
    """
    Fetch all predictions for a given experiment/season/week.

    Season and week are required partition filters on experiments.backtest_predictions.
    """
    query = f"""
        SELECT
          game_id,
          week,
          home_team,
          away_team,
          predicted_home_cover_prob,
          predicted_side,
          actual_home_covered,
          correct,
          -- confidence_tier is part of the API contract and the response schema,
          -- but was never selected here, so it was null on every prediction ever
          -- served. The frontend's ConfidenceBadge called tier.charAt(0) on it
          -- and took the whole dashboard down with a white screen the moment
          -- predictions started being returned.
          --
          -- Distance from a coin flip, not raw probability: 0.55 and 0.45 are
          -- equally confident calls in opposite directions.
          CASE
            WHEN ABS(predicted_home_cover_prob - 0.5) >= 0.10 THEN 'high'
            WHEN ABS(predicted_home_cover_prob - 0.5) >= 0.05 THEN 'medium'
            ELSE 'low'
          END AS confidence_tier
        FROM `{PROJECT}.experiments.backtest_predictions`
        WHERE experiment_id = @experiment_id
          AND season = @season
          AND week = @week
        ORDER BY game_id
    """
    params = [
        bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
        bigquery.ScalarQueryParameter("season", "INT64", season),
        bigquery.ScalarQueryParameter("week", "INT64", week),
    ]

    rows = _run_query(client, query, params)
    return rows


# ── Trigger the refresh job ───────────────────────────────────────────────────


REFRESH_JOB_NAME = "nfl-production-refresh"
REFRESH_JOB_REGION = "us-central1"


def trigger_prediction_refresh(season: int, week: int | None = None) -> str:
    """
    Execute the nfl-production-refresh Cloud Run Job.

    Same mechanism as trigger_experiment_runner: a direct call to the Cloud Run
    Jobs API using the service's own credentials, with environment overrides.
    The job grades any finished week and predicts the next unplayed one; passing
    a week pins it to that week instead of letting the job choose.

    Returns the execution name so the caller can report it.
    """
    import google.auth
    import google.auth.transport.requests
    import requests as http_requests

    credentials, project = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())

    url = (
        f"https://{REFRESH_JOB_REGION}-run.googleapis.com/apis/run.googleapis.com/v1/"
        f"namespaces/{project}/jobs/{REFRESH_JOB_NAME}:run"
    )

    env = [{"name": "REFRESH_SEASON", "value": str(season)}]
    if week is not None:
        env.append({"name": "REFRESH_WEEK", "value": str(week)})

    resp = http_requests.post(
        url,
        json={"overrides": {"containerOverrides": [{"env": env}]}},
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("metadata", {}).get("name", "unknown")

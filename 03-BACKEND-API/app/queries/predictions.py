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
    Find the production experiment (most recent gate-passed run).

    If experiment_id_override is provided, fetch that specific experiment and
    verify it has gate_passed = true. Return None if not gate-passed or not found.

    Returns a dict with: experiment_id, run_id, completed_at, experiment_name
    """
    if experiment_id_override:
        query = f"""
            SELECT
              r.experiment_id,
              r.run_id,
              FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', r.completed_at) AS completed_at,
              c.name AS experiment_name
            FROM `{PROJECT}.experiments.backtest_runs` r
            JOIN `{PROJECT}.platform.experiment_configs` c
              ON r.experiment_id = c.experiment_id
            WHERE r.experiment_id = @experiment_id
              AND r.gate_passed = true
              AND c.gate_passed = true
            ORDER BY r.completed_at DESC
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id_override)]
    else:
        query = f"""
            SELECT
              r.experiment_id,
              r.run_id,
              FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', r.completed_at) AS completed_at,
              c.name AS experiment_name
            FROM `{PROJECT}.experiments.backtest_runs` r
            JOIN `{PROJECT}.platform.experiment_configs` c
              ON r.experiment_id = c.experiment_id
            WHERE r.gate_passed = true
              AND c.gate_passed = true
            ORDER BY r.completed_at DESC
            LIMIT 1
        """
        params = []

    rows = _run_query(client, query, params)
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
          confidence_tier
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

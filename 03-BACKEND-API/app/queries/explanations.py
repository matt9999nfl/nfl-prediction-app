"""
BigQuery queries for GET /api/v1/predictions/{game_id}/explanation.

Reads experiments.prediction_explanations — one row per (game, feature),
written by 02-MODELING/backtests/explanations_bq.py.
"""
import logging
from typing import Any

from google.cloud import bigquery

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT = settings.bigquery_project


def _run_query(
    client: bigquery.Client,
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(query, job_config=job_config).result())
    return [dict(row) for row in rows]


def get_game_explanation_rows(
    client: bigquery.Client,
    experiment_id: str,
    game_id: str,
) -> list[dict[str, Any]]:
    """
    All (feature) rows for one game under one experiment, ordered by
    |contribution| (abs_rank). Empty list means no explanation is stored for
    this game/experiment — the router turns that into a 404.
    """
    query = f"""
        SELECT
          run_id, model_name, predicted_side, predicted_home_cover_prob,
          bias_logodds, clean_forward, is_approximate, reproduction_max_diff,
          feature, side, family, raw_value, league_pctile, was_imputed,
          contribution_logodds, pick_direction_contribution, abs_rank
        FROM `{PROJECT}.experiments.prediction_explanations`
        WHERE experiment_id = @experiment_id
          AND game_id = @game_id
        ORDER BY abs_rank
    """
    params = [
        bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
        bigquery.ScalarQueryParameter("game_id", "STRING", game_id),
    ]
    return _run_query(client, query, params)

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

    A game can carry more than one explanation run (explain_picks.py appends
    an exact backfill without deleting an earlier approximate one — never
    deletes). This serves exactly one run: exact over approximate, then the
    newest by created_at. The live pick's side is joined in from
    experiments.backtest_predictions as `live_predicted_side` — the router
    uses it to make the live pick authoritative (heading, warning, and
    pick-direction re-signing) even when this run's own `predicted_side`
    leans the other way.
    """
    query = f"""
        WITH best_run AS (
          SELECT run_id
          FROM `{PROJECT}.experiments.prediction_explanations`
          WHERE experiment_id = @experiment_id AND game_id = @game_id
          GROUP BY run_id
          ORDER BY LOGICAL_OR(is_approximate) ASC, MAX(created_at) DESC
          LIMIT 1
        )
        SELECT
          pe.run_id, pe.model_name, pe.predicted_side, pe.predicted_home_cover_prob,
          pe.bias_logodds, pe.clean_forward, pe.is_approximate, pe.reproduction_max_diff,
          pe.feature, pe.side, pe.family, pe.raw_value, pe.league_pctile, pe.was_imputed,
          pe.contribution_logodds, pe.pick_direction_contribution, pe.abs_rank,
          COALESCE(bp.predicted_side, pe.predicted_side) AS live_predicted_side
        FROM `{PROJECT}.experiments.prediction_explanations` pe
        JOIN best_run USING (run_id)
        LEFT JOIN `{PROJECT}.experiments.backtest_predictions` bp
          ON bp.experiment_id = pe.experiment_id AND bp.game_id = pe.game_id
        WHERE pe.experiment_id = @experiment_id AND pe.game_id = @game_id
        ORDER BY pe.abs_rank
    """
    params = [
        bigquery.ScalarQueryParameter("experiment_id", "STRING", experiment_id),
        bigquery.ScalarQueryParameter("game_id", "STRING", game_id),
    ]
    return _run_query(client, query, params)

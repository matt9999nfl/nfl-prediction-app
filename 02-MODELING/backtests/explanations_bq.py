"""
BigQuery storage for experiments.prediction_explanations (STAGE 1.3 of
PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md).

One row per (game, feature): the long-format output of
backtests.explanations.build_explanations(), plus run/model identity columns.
Partitioned by season, clustered by (experiment_id, week) — the same shape as
experiments.backtest_predictions in bq_writer.py, for the same reason: the
API's hot query is "this experiment, this week".

No JSON columns, so writes use load_table_from_dataframe (pyarrow handles
primitive types natively) — same choice bq_writer.py makes for
backtest_predictions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
DATASET = "experiments"
EXPLANATIONS_TABLE = f"{PROJECT}.{DATASET}.prediction_explanations"

EXPLANATIONS_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("experiment_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("season", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("week", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("game_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("feature", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("side", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("family", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("raw_value", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("league_pctile", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("was_imputed", "BOOL", mode="REQUIRED"),
    bigquery.SchemaField("contribution_logodds", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("pick_direction_contribution", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("abs_rank", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("bias_logodds", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("model_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("feature_list_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("blend_n", "INT64", mode="NULLABLE"),
    bigquery.SchemaField("predicted_side", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("predicted_home_cover_prob", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("clean_forward", "BOOL", mode="NULLABLE"),
    # reproduction_max_diff / is_approximate are about explain_picks.py's
    # reproduction guard (STAGE 1.6) — how far the retrained model's
    # probabilities were from the stored picks, and whether this row was
    # written anyway via --approximate despite the guard failing. NULL /
    # False respectively on the live path (predict_upcoming.py), which never
    # runs the guard at all. Deliberately separate from clean_forward, which
    # keeps its one meaning: not regenerated after kickoff.
    bigquery.SchemaField("reproduction_max_diff", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("is_approximate", "BOOL", mode="REQUIRED"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

_OUTPUT_COLUMNS = [
    "game_id", "feature", "side", "family", "raw_value", "league_pctile",
    "was_imputed", "contribution_logodds", "pick_direction_contribution",
    "abs_rank", "bias_logodds", "predicted_side", "predicted_home_cover_prob",
]


def ensure_explanations_table(client: bigquery.Client) -> None:
    """Idempotently create the dataset/table. Safe to call every run."""
    ds_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds_ref.location = "US"
    client.create_dataset(ds_ref, exists_ok=True)

    table = bigquery.Table(EXPLANATIONS_TABLE, schema=EXPLANATIONS_SCHEMA)
    table.range_partitioning = bigquery.RangePartitioning(
        field="season",
        range_=bigquery.PartitionRange(start=2010, end=2040, interval=1),
    )
    table.clustering_fields = ["experiment_id", "week"]
    client.create_table(table, exists_ok=True)
    logger.info("Table ready: %s", EXPLANATIONS_TABLE)


def write_explanations(
    client: bigquery.Client,
    exp_df: pd.DataFrame,
    *,
    run_id: str,
    experiment_id: str,
    model_name: str,
    feature_list_hash: str,
    blend_n: int | None,
    clean_forward: bool | dict | None = None,
    reproduction_max_diff: float | None = None,
    is_approximate: bool = False,
) -> int:
    """
    Append exp_df (the output of backtests.explanations.build_explanations,
    which carries game_id/season/week/feature/... already) to
    experiments.prediction_explanations.

    clean_forward: either a single bool applied to every row, a
    {game_id: bool} mapping (explain_picks.py backfill, per-game), or None
    (left NULL — the live path where every row is a normal, not-yet-flagged
    forward pick). Means ONLY "not regenerated after kickoff" — never
    repurposed to mean anything about reproduction.

    reproduction_max_diff / is_approximate: explain_picks.py's reproduction
    guard result for this write (a single value applied to every row of the
    write, since the guard runs once per week, not per game). Left at their
    defaults (None / False) on the live path, which never runs the guard.

    Returns the number of rows written.
    """
    missing = [c for c in _OUTPUT_COLUMNS if c not in exp_df.columns]
    if missing:
        raise ValueError(f"exp_df is missing columns required for storage: {missing}")
    if "season" not in exp_df.columns or "week" not in exp_df.columns:
        raise ValueError("exp_df must carry season and week (from games_meta merge)")

    out = exp_df[["season", "week"] + _OUTPUT_COLUMNS].copy()
    out.insert(0, "experiment_id", experiment_id)
    out.insert(0, "run_id", run_id)
    out["model_name"] = model_name
    out["feature_list_hash"] = feature_list_hash
    out["blend_n"] = blend_n

    if clean_forward is None:
        out["clean_forward"] = pd.array([pd.NA] * len(out), dtype="boolean")
    elif isinstance(clean_forward, dict):
        out["clean_forward"] = out["game_id"].map(clean_forward).astype("boolean")
    else:
        out["clean_forward"] = bool(clean_forward)

    repro_val = float(reproduction_max_diff) if reproduction_max_diff is not None else pd.NA
    out["reproduction_max_diff"] = pd.array([repro_val] * len(out), dtype="Float64")
    out["is_approximate"] = bool(is_approximate)

    out["created_at"] = datetime.now(timezone.utc)
    out["was_imputed"] = out["was_imputed"].astype(bool)
    out["abs_rank"] = out["abs_rank"].astype("int64")
    out["season"] = out["season"].astype("int64")
    out["week"] = out["week"].astype("int64")

    job = client.load_table_from_dataframe(
        out,
        EXPLANATIONS_TABLE,
        job_config=bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            schema=EXPLANATIONS_SCHEMA,
        ),
    )
    job.result()
    logger.info(
        "prediction_explanations: wrote %d rows (run_id=%s, experiment_id=%s)",
        len(out), run_id, experiment_id,
    )
    return len(out)


def delete_week_explanations(
    client: bigquery.Client, experiment_id: str, season: int, week: int,
) -> None:
    """
    Delete-then-insert companion for the live path — mirrors
    predict_upcoming.replace_week_predictions so a re-run mid-week never
    leaves two generations of explanation for the same game.
    """
    query = f"""
        DELETE FROM `{EXPLANATIONS_TABLE}`
        WHERE experiment_id = @eid AND season = @season AND week = @week
    """
    client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("eid", "STRING", experiment_id),
                bigquery.ScalarQueryParameter("season", "INT64", season),
                bigquery.ScalarQueryParameter("week", "INT64", week),
            ]
        ),
    ).result()


def delete_kicked_off_games(
    client: bigquery.Client, experiment_id: str, season: int, week: int, kicked_off_game_ids: list[str],
) -> None:
    """
    Delete only the NOT-kicked-off games' explanations for a week, leaving
    kicked-off games' rows untouched — the explanation-layer equivalent of
    "never rewrite a pick or explanation for a game that has kicked off."
    Callers re-insert the not-kicked-off games after calling this.
    """
    if not kicked_off_game_ids:
        delete_week_explanations(client, experiment_id, season, week)
        return
    query = f"""
        DELETE FROM `{EXPLANATIONS_TABLE}`
        WHERE experiment_id = @eid AND season = @season AND week = @week
          AND game_id NOT IN UNNEST(@kicked_off)
    """
    client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("eid", "STRING", experiment_id),
                bigquery.ScalarQueryParameter("season", "INT64", season),
                bigquery.ScalarQueryParameter("week", "INT64", week),
                bigquery.ArrayQueryParameter("kicked_off", "STRING", kicked_off_game_ids),
            ]
        ),
    ).result()

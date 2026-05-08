"""
BigQuery output layer for backtest results.

Writes to two tables in the `experiments` dataset:
  experiments.backtest_runs        — one row per full backtest run
  experiments.backtest_predictions — one row per game per fold

Schema design (Phase 2+):
  experiment_id  = the experiment config UUID (links to platform.experiment_configs)
  run_id         = unique run identifier (NFL_RUN_ID from env, or runner-generated fallback)

  backtest_predictions also stores run_id so the API can join:
    SELECT ... FROM backtest_predictions WHERE run_id = (
        SELECT run_id FROM backtest_runs WHERE experiment_id = ? ORDER BY run_at DESC LIMIT 1
    )

Tables are created idempotently via setup_experiments_tables().
Phase 2 ALTER TABLE calls are omitted — all columns exist in the current table schema.
"""

import json
import logging
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)

PROJECT  = "nfl-model-471509"
DATASET  = "experiments"
RUNS_TABLE  = f"{PROJECT}.{DATASET}.backtest_runs"
PREDS_TABLE = f"{PROJECT}.{DATASET}.backtest_predictions"


# ── Schema definitions ────────────────────────────────────────────────────────
#
# experiment_id is ALWAYS the experiment config UUID (from platform.experiment_configs).
# run_id        is a unique run identifier (NFL_RUN_ID env var or runner-generated).
#
# All metric fields are NULLABLE so partial/failed runs can still write a row.

RUNS_SCHEMA = [
    bigquery.SchemaField("run_id",               "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("experiment_id",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("name",                 "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("run_at",               "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("completed_at",         "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("model_type",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("features",             "JSON",      mode="NULLABLE"),
    bigquery.SchemaField("status",               "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("ats_hit_rate",         "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("ats_record_wins",      "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("ats_record_losses",    "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("ats_record_pushes",    "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("n_games_evaluated",    "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("gate_passed",          "BOOL",      mode="NULLABLE"),
    bigquery.SchemaField("training_window_years","INT64",     mode="NULLABLE"),
    bigquery.SchemaField("seasons_evaluated",    "JSON",      mode="NULLABLE"),
    bigquery.SchemaField("folds_complete",       "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("folds_total",          "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("error_message",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("notes",                "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("success_criteria",     "JSON",      mode="NULLABLE"),
    bigquery.SchemaField("feature_importances",  "JSON",      mode="NULLABLE"),
]

PREDS_SCHEMA = [
    bigquery.SchemaField("run_id",                    "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("experiment_id",             "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("fold",                      "INT64",   mode="REQUIRED"),
    bigquery.SchemaField("game_id",                   "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("season",                    "INT64",   mode="REQUIRED"),
    bigquery.SchemaField("week",                      "INT64",   mode="REQUIRED"),
    bigquery.SchemaField("home_team",                 "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("away_team",                 "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("home_spread_close",         "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("predicted_home_cover_prob", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("predicted_side",            "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("actual_home_covered",       "BOOL",    mode="NULLABLE"),
    bigquery.SchemaField("correct",                   "INT64",   mode="NULLABLE"),
    bigquery.SchemaField("ol_mismatch_flag",          "INT64",   mode="REQUIRED"),
]


def _alter_predictions_table(client: bigquery.Client) -> None:
    """
    Idempotently add run_id to experiments.backtest_predictions.
    Safe to call repeatedly — BigQuery skips columns that already exist.
    """
    ddl = (
        f"ALTER TABLE `{PREDS_TABLE}` "
        f"ADD COLUMN IF NOT EXISTS `run_id` STRING"
    )
    try:
        client.query(ddl).result()
        logger.info("backtest_predictions: ensured column run_id (STRING)")
    except Exception as e:
        logger.warning(f"backtest_predictions: ALTER TABLE for run_id raised: {e}")


def _ensure_dataset(client: bigquery.Client) -> None:
    ds_ref = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds_ref.location = "US"
    client.create_dataset(ds_ref, exists_ok=True)
    logger.info(f"Dataset ready: {DATASET}")


def _ensure_table(
    client: bigquery.Client,
    table_id: str,
    schema: list,
    partition_field: str,
    clustering_fields: list[str] | None = None,
) -> None:
    table = bigquery.Table(table_id, schema=schema)
    if partition_field == "season":
        table.range_partitioning = bigquery.RangePartitioning(
            field="season",
            range_=bigquery.PartitionRange(start=2010, end=2040, interval=1),
        )
    if clustering_fields:
        table.clustering_fields = clustering_fields
    client.create_table(table, exists_ok=True)
    logger.info(f"Table ready: {table_id}")


def write_backtest_run(
    client: bigquery.Client,
    result,                           # BacktestResult from walk_forward
    features_used: list[str],
    notes: str = "",
    training_window_years: int = 4,
    # Identity fields — experiment_config_id is the config UUID from experiment_configs
    run_id: str | None = None,
    experiment_config_id: str | None = None,
    success_criteria: dict | None = None,
    folds_complete: int | None = None,
    folds_total: int | None = None,
    completed_at=None,                # datetime; defaults to now()
    error_message: str | None = None,
    feature_importances: dict | None = None,
) -> None:
    """Insert one row into experiments.backtest_runs.

    experiment_id in the written row is set to experiment_config_id (the config UUID)
    when provided, so the API's WHERE experiment_id = <config UUID> queries find it.

    run_id is the NFL_RUN_ID passed from the API (or the runner's internal ID as fallback).
    It is also written to backtest_predictions so the API can join the two tables.
    """
    test_seasons = [fr.test_season for fr in result.folds]

    # experiment_id in backtest_runs must be the config UUID so the API can find it.
    # Fall back to result.experiment_id (runner's internal ID) for Phase 1 compatibility.
    experiment_id_to_write = experiment_config_id or result.experiment_id

    # run_id uniquely identifies this run; used as the join key to backtest_predictions.
    run_id_to_write = run_id or result.experiment_id

    row = {
        "run_id":                run_id_to_write,
        "experiment_id":         experiment_id_to_write,
        "name":                  result.name,
        "run_at":                datetime.now(timezone.utc),
        "completed_at":          completed_at or datetime.now(timezone.utc),
        "model_type":            "xgboost",
        "features":              json.dumps(features_used),
        "status":                "failed" if error_message else "complete",
        "ats_hit_rate":          result.overall_hit_rate,
        "ats_record_wins":       result.total_wins,
        "ats_record_losses":     result.total_losses,
        "ats_record_pushes":     result.total_pushes,
        "n_games_evaluated":     result.total_n_games,
        "gate_passed":           result.gate_passed,
        "training_window_years": training_window_years,
        "seasons_evaluated":     json.dumps(test_seasons),
        "folds_complete":        folds_complete,
        "folds_total":           folds_total,
        "error_message":         error_message,
        "notes":                 notes or None,
        "success_criteria":      json.dumps(success_criteria) if success_criteria is not None else None,
        "feature_importances":   json.dumps(feature_importances) if feature_importances is not None else None,
    }

    df = pd.DataFrame([row])
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=RUNS_SCHEMA,
    )
    job = client.load_table_from_dataframe(df, RUNS_TABLE, job_config=job_config)
    job.result()
    logger.info(f"backtest_runs: wrote 1 row for experiment {result.experiment_id}")


def write_backtest_predictions(
    client: bigquery.Client,
    result,           # BacktestResult from walk_forward
    run_id: str | None = None,
    experiment_config_id: str | None = None,
) -> None:
    """
    Insert all fold predictions into experiments.backtest_predictions.

    run_id and experiment_id must match what was written to backtest_runs so the
    API can join: backtest_predictions.run_id = backtest_runs.run_id.
    """
    all_preds = result.all_predictions()

    preds_out = all_preds[[
        "game_id", "season", "week", "home_team", "away_team",
        "home_spread_close", "predicted_home_cover_prob", "predicted_side",
        "actual_home_covered", "correct", "ol_mismatch_flag", "fold",
    ]].copy()

    # experiment_id must be the config UUID so the API's WHERE clause finds it.
    preds_out.insert(0, "experiment_id", experiment_config_id or result.experiment_id)
    # run_id is the join key to backtest_runs.
    preds_out.insert(0, "run_id", run_id or result.experiment_id)

    # actual_home_covered must be nullable bool; correct must be nullable Int64
    preds_out["actual_home_covered"] = preds_out["actual_home_covered"].astype(object)
    preds_out["correct"] = preds_out["correct"].astype(object)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=PREDS_SCHEMA,
    )
    job = client.load_table_from_dataframe(preds_out, PREDS_TABLE, job_config=job_config)
    job.result()
    logger.info(
        f"backtest_predictions: wrote {len(preds_out):,} rows "
        f"(experiment_id={experiment_config_id or result.experiment_id}, run_id={run_id or result.experiment_id})"
    )


def setup_experiments_tables(client: bigquery.Client) -> None:
    """Idempotently create/update the experiments dataset and both output tables.

    backtest_runs already contains all required columns (including run_id, status,
    feature_importances, etc.) from the Phase 2+ schema recreation.

    backtest_predictions gets run_id added idempotently via ALTER TABLE.
    """
    _ensure_dataset(client)
    _ensure_table(
        client, RUNS_TABLE, RUNS_SCHEMA,
        partition_field="none",   # no partitioning on runs table (small)
        clustering_fields=None,
    )
    _ensure_table(
        client, PREDS_TABLE, PREDS_SCHEMA,
        partition_field="season",
        clustering_fields=["experiment_id", "fold"],
    )
    # Ensure run_id exists in predictions (safe to call repeatedly)
    _alter_predictions_table(client)

"""
BigQuery output layer for backtest results.

Writes to two tables in the `experiments` dataset:
  experiments.backtest_runs        — one row per full backtest run
  experiments.backtest_predictions — one row per game per fold

Schema matches MODELING_SPEC_PHASE1.md for Phase 1 columns.
Phase 2 additions (PIPELINE_SCHEMA_MIGRATION_PHASE2.md):
  backtest_runs gets six new columns:
    experiment_config_id  STRING   NULLABLE  (added by DATA-PIPELINE migrate_phase2.py)
    success_criteria      JSON     NULLABLE  (added by DATA-PIPELINE migrate_phase2.py)
    folds_complete        INT64    NULLABLE  (added by _alter_runs_table_phase2 below)
    folds_total           INT64    NULLABLE  (added by _alter_runs_table_phase2 below)
    completed_at          TIMESTAMP NULLABLE (added by _alter_runs_table_phase2 below)
    error_message         STRING   NULLABLE  (added by _alter_runs_table_phase2 below)

Tables are created (or altered) idempotently via setup_experiments_tables().
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

RUNS_SCHEMA = [
    # ── Phase 1 columns (original) ────────────────────────────────────────────
    bigquery.SchemaField("experiment_id",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("name",                 "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("run_at",               "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("model_type",           "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("features",             "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("training_window_years","INT64",     mode="REQUIRED"),
    bigquery.SchemaField("seasons_evaluated",    "JSON",      mode="REQUIRED"),
    bigquery.SchemaField("ats_record_wins",      "INT64",     mode="REQUIRED"),
    bigquery.SchemaField("ats_record_losses",    "INT64",     mode="REQUIRED"),
    bigquery.SchemaField("ats_record_pushes",    "INT64",     mode="REQUIRED"),
    bigquery.SchemaField("ats_hit_rate",         "FLOAT64",   mode="REQUIRED"),
    bigquery.SchemaField("n_games_evaluated",    "INT64",     mode="REQUIRED"),
    bigquery.SchemaField("gate_passed",          "BOOL",      mode="REQUIRED"),
    bigquery.SchemaField("notes",                "STRING",    mode="NULLABLE"),
    # ── Phase 2 columns — added by DATA-PIPELINE migrate_phase2.py ───────────
    bigquery.SchemaField("experiment_config_id", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("success_criteria",     "JSON",      mode="NULLABLE"),
    # ── Phase 2 columns — added by _alter_runs_table_phase2() below ──────────
    bigquery.SchemaField("folds_complete",       "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("folds_total",          "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("completed_at",         "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("error_message",        "STRING",    mode="NULLABLE"),
    # ── Phase 3 columns — added by _alter_runs_table_phase3() below ──────────
    bigquery.SchemaField("feature_importances",  "JSON",      mode="NULLABLE"),
]

# Columns that _alter_runs_table_phase2() must ADD to the live table.
# experiment_config_id and success_criteria were already added by DATA-PIPELINE.
_PHASE2_NEW_COLUMNS: list[tuple[str, str]] = [
    ("folds_complete", "INT64"),
    ("folds_total",    "INT64"),
    ("completed_at",   "TIMESTAMP"),
    ("error_message",  "STRING"),
]

# Columns that _alter_runs_table_phase3() must ADD to the live table.
_PHASE3_NEW_COLUMNS: list[tuple[str, str]] = [
    ("feature_importances", "JSON"),
]

PREDS_SCHEMA = [
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


def _alter_runs_table_phase2(client: bigquery.Client) -> None:
    """
    Idempotently add the four Phase 2 columns to experiments.backtest_runs.

    BigQuery's create_table(exists_ok=True) does NOT add columns to an
    existing table, so we issue explicit ALTER TABLE … ADD COLUMN IF NOT EXISTS
    statements.  Safe to call repeatedly — BigQuery silently skips columns
    that already exist.
    """
    for col_name, col_type in _PHASE2_NEW_COLUMNS:
        ddl = (
            f"ALTER TABLE `{RUNS_TABLE}` "
            f"ADD COLUMN IF NOT EXISTS `{col_name}` {col_type}"
        )
        try:
            client.query(ddl).result()
            logger.info(f"backtest_runs: ensured column {col_name} ({col_type})")
        except Exception as e:
            # Log but don't hard-fail — column may already exist in a form BQ
            # considers incompatible with the IF NOT EXISTS path.
            logger.warning(f"backtest_runs: ALTER TABLE for {col_name} raised: {e}")


def _alter_runs_table_phase3(client: bigquery.Client) -> None:
    """
    Idempotently add the Phase 3 columns to experiments.backtest_runs.

    BigQuery's create_table(exists_ok=True) does NOT add columns to an
    existing table, so we issue explicit ALTER TABLE … ADD COLUMN IF NOT EXISTS
    statements.  Safe to call repeatedly — BigQuery silently skips columns
    that already exist.
    """
    for col_name, col_type in _PHASE3_NEW_COLUMNS:
        ddl = (
            f"ALTER TABLE `{RUNS_TABLE}` "
            f"ADD COLUMN IF NOT EXISTS `{col_name}` {col_type}"
        )
        try:
            client.query(ddl).result()
            logger.info(f"backtest_runs: ensured column {col_name} ({col_type})")
        except Exception as e:
            # Log but don't hard-fail — column may already exist in a form BQ
            # considers incompatible with the IF NOT EXISTS path.
            logger.warning(f"backtest_runs: ALTER TABLE for {col_name} raised: {e}")


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
    # Phase 2 fields — all optional so Phase 1 runner works unchanged
    experiment_config_id: str | None = None,
    success_criteria: dict | None = None,
    folds_complete: int | None = None,
    folds_total: int | None = None,
    completed_at=None,                # datetime; defaults to now()
    error_message: str | None = None,
    # Phase 3 fields
    feature_importances: dict | None = None,
) -> None:
    """Insert one row into experiments.backtest_runs.

    Phase 1 callers omit all keyword arguments after ``notes``.
    Phase 2 config-driven callers pass the additional fields.
    Phase 3 callers can pass feature_importances dict.
    """
    test_seasons = [fr.test_season for fr in result.folds]

    row = {
        # Phase 1 columns
        "experiment_id":         result.experiment_id,
        "name":                  result.name,
        "run_at":                datetime.now(timezone.utc),
        "model_type":            "xgboost",
        "features":              json.dumps(features_used),
        "training_window_years": training_window_years,
        "seasons_evaluated":     json.dumps(test_seasons),
        "ats_record_wins":       result.total_wins,
        "ats_record_losses":     result.total_losses,
        "ats_record_pushes":     result.total_pushes,
        "ats_hit_rate":          result.overall_hit_rate,
        "n_games_evaluated":     result.total_n_games,
        "gate_passed":           result.gate_passed,
        "notes":                 notes or None,
        # Phase 2 columns
        "experiment_config_id":  experiment_config_id,
        "success_criteria":      json.dumps(success_criteria) if success_criteria is not None else None,
        "folds_complete":        folds_complete,
        "folds_total":           folds_total,
        "completed_at":          completed_at or datetime.now(timezone.utc),
        "error_message":         error_message,
        # Phase 3 columns
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
) -> None:
    """
    Insert all fold predictions into experiments.backtest_predictions.
    Written season-by-season (one BQ load job per test season).
    """
    all_preds = result.all_predictions()

    # Ensure column set and types match schema
    all_preds = all_preds.rename(columns={"actual_home_covered": "actual_home_covered"})
    preds_out = all_preds[[
        "game_id", "season", "week", "home_team", "away_team",
        "home_spread_close", "predicted_home_cover_prob", "predicted_side",
        "actual_home_covered", "correct", "ol_mismatch_flag", "fold",
    ]].copy()
    preds_out.insert(0, "experiment_id", result.experiment_id)

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
        f"backtest_predictions: wrote {len(preds_out):,} rows for experiment {result.experiment_id}"
    )


def setup_experiments_tables(client: bigquery.Client) -> None:
    """Idempotently create/update the experiments dataset and both output tables.

    Phase 2 note: also issues ALTER TABLE statements to add the four new
    columns (folds_complete, folds_total, completed_at, error_message) that
    BACKEND-API's status-polling endpoint requires.  Safe to call repeatedly.

    Phase 3 note: also issues ALTER TABLE statements to add feature_importances
    column for persisting XGBoost feature importance scores.
    """
    _ensure_dataset(client)
    _ensure_table(
        client, RUNS_TABLE, RUNS_SCHEMA,
        partition_field="none",   # no partitioning on runs table (small)
        clustering_fields=None,
    )
    # Add the four new Phase 2 columns — no-op if they already exist.
    _alter_runs_table_phase2(client)
    # Add Phase 3 columns — no-op if they already exist.
    _alter_runs_table_phase3(client)
    _ensure_table(
        client, PREDS_TABLE, PREDS_SCHEMA,
        partition_field="season",
        clustering_fields=["experiment_id", "fold"],
    )

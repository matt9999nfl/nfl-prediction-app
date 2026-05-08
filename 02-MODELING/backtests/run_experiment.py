"""
Config-driven Experiment Runner — Phase 2 entry point.

Reads EXPERIMENT_CONFIG_ID from the environment, loads the corresponding row
from ``platform.experiment_configs`` in BigQuery, builds the feature matrix
dynamically, runs the walk-forward backtest, writes results, and updates the
config row with the outcome.

Invocation
----------
    cd 02-MODELING
    EXPERIMENT_CONFIG_ID=<uuid> python backtests/run_experiment.py

This is the script that BACKEND-API's stub triggers (or calls via subprocess /
Cloud Run job).  No other arguments are required.

Design
------
1.  Load ExperimentConfig from ``platform.experiment_configs``.
2.  Parse the four JSON columns: features, evaluation, methodology, model.
3.  Load base data from BigQuery (curated.plays + curated.games).
4.  Build feature matrix:
      - curated features: compute all 52 features via existing builders, then
        select only the columns listed in the config.
      - user_datasets.* features: query directly and left-join on the
        appropriate join key (game_id or team+season+week), null-fill with 0.
5.  Run walk-forward using folds derived from methodology config.
6.  Write results to BigQuery (experiments.backtest_runs + predictions).
7.  In a finally block, update platform.experiment_configs with status,
    gate_passed, latest_run_id, run_count.

Ambiguities resolved (see PROJECT-LEAD report at end of file)
--------------------------------------------------------------
- Feature column names in config are base per-team names (e.g. ol_sack_rate).
  The runner auto-adds home_/away_ prefixes for per-team features.
  Game-context features (home_advantage, div_game, roof_dome, temp, wind,
  rest_differential) are always included and are NOT listed in config features.
- model.type is a string key mapped to a class via MODEL_REGISTRY.
- evaluation.success_threshold maps to gate_hit_rate; evaluation.min_sample
  maps to gate_min_games.
- methodology.train_seasons and test_seasons are integers (count of seasons),
  not lists.
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from google.cloud import bigquery

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.ol_metrics import (
    load_plays,
    load_games,
    compute_season_to_date_features,
    build_game_feature_matrix,
    ALL_TEAM_RATE_FEATURES,
    GAME_CONTEXT_FEATURES,
)
from features.comprehensive import (
    compute_additional_team_features,
    ALL_ADDITIONAL_TEAM_FEATURES,
)
from features.situational import (
    compute_situational_features,
    add_rest_differential,
    SITUATIONAL_TEAM_FEATURES,
)
from backtests.walk_forward import (
    run_walk_forward,
    build_folds_from_config,
    format_backtest_report,
    PHASE2_GATE_HIT_RATE,
    PHASE2_GATE_MIN_GAMES,
)
from backtests.bq_writer import (
    setup_experiments_tables,
    write_backtest_run,
    write_backtest_predictions,
)
from models.xgb_v2 import OLXGBModelV2
from models.ol_xgb import OLXGBModel

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PROJECT          = "nfl-model-471509"
REPORTS_DIR      = ROOT / "backtests" / "reports"
EXPERIMENTS_LOG  = ROOT / "experiments" / "EXPERIMENTS.md"

# Every per-team feature name the existing builders can produce.
# Used to distinguish curated per-team features from game-context features.
ALL_CURATED_TEAM_FEATURES: list[str] = (
    ALL_TEAM_RATE_FEATURES           # 12 OL + defense features from ol_metrics
    + ALL_ADDITIONAL_TEAM_FEATURES   # 8 comprehensive features
    + SITUATIONAL_TEAM_FEATURES      # 3 situational features
)

# Model type string → class mapping.
#
# "xgboost" is the abstract type name the API contract / dashboard stores.
#   → resolves to OLXGBModelV2, the current production-quality implementation.
# "ol_xgb_v1" / "ol_xgb_v2" are kept for backward compat with Phase 1 rows
#   already written to experiments.backtest_runs.
# "logistic_regression" / "random_forest" are reserved stubs: they fail with
#   a clear NotImplementedError rather than a cryptic KeyError so future
#   configs using those types surface a meaningful message immediately.

def _not_implemented(name: str):
    """Return a fake class whose instantiation raises NotImplementedError."""
    class _Stub:
        def __init__(self, *a, **kw):
            raise NotImplementedError(
                f"Model type {name!r} is not yet implemented in the Experiment Runner. "
                "Open a ticket or implement the model class and add it to MODEL_REGISTRY."
            )
    _Stub.__name__ = name
    return _Stub


MODEL_REGISTRY: dict[str, type] = {
    # ── API / dashboard type name ─────────────────────────────────────────────
    "xgboost":            OLXGBModelV2,   # default for all FRONTEND-created configs
    # ── Phase 1 legacy keys (backward compat) ────────────────────────────────
    "ol_xgb_v1":          OLXGBModel,
    "ol_xgb_v2":          OLXGBModelV2,
    # ── Reserved stubs — fail informatively, not with KeyError ───────────────
    "logistic_regression": _not_implemented("logistic_regression"),
    "random_forest":       _not_implemented("random_forest"),
}

# BigQuery table IDs
EXPERIMENT_CONFIGS_TABLE = f"{PROJECT}.platform.experiment_configs"
DATASETS_TABLE           = f"{PROJECT}.platform.datasets"


# ── Config loading ────────────────────────────────────────────────────────────

def load_experiment_config(client: bigquery.Client, experiment_config_id: str) -> dict:
    """
    Load one row from platform.experiment_configs and return it as a dict
    with the four JSON columns already parsed into Python objects.

    Raises ValueError if the row is not found.
    """
    query = f"""
        SELECT
            experiment_id,
            name,
            description,
            target,
            features,
            evaluation,
            methodology,
            model,
            status,
            gate_passed,
            latest_run_id,
            run_count
        FROM `{EXPERIMENT_CONFIGS_TABLE}`
        WHERE experiment_id = @config_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("config_id", "STRING", experiment_config_id)
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    if not rows:
        raise ValueError(
            f"No experiment config found for experiment_id={experiment_config_id!r}"
        )

    row = dict(rows[0])
    # Parse JSON columns from strings into Python objects
    for col in ("features", "evaluation", "methodology", "model"):
        val = row.get(col)
        if isinstance(val, str):
            row[col] = json.loads(val)
        # If already a dict/list (BigQuery JSON type may auto-parse) leave as-is.

    logger.info(f"Loaded config: {row['name']!r} (id={experiment_config_id})")
    return row


# ── Status helpers ────────────────────────────────────────────────────────────

def _set_config_running(client: bigquery.Client, experiment_config_id: str) -> None:
    """Mark the config row as running before the backtest starts."""
    ddl = f"""
        UPDATE `{EXPERIMENT_CONFIGS_TABLE}`
        SET status = 'running',
            updated_at = CURRENT_TIMESTAMP()
        WHERE experiment_id = @config_id
    """
    _run_dml(client, ddl, experiment_config_id)
    logger.info("experiment_configs: status → running")


def _set_config_done(
    client: bigquery.Client,
    experiment_config_id: str,
    run_id: str,
    gate_passed: bool,
    error_message: Optional[str] = None,
) -> None:
    """
    Update status, gate_passed, latest_run_id, and run_count at completion.
    Called from the finally block whether the run succeeded or failed.
    """
    status = "failed" if error_message else "complete"
    ddl = f"""
        UPDATE `{EXPERIMENT_CONFIGS_TABLE}`
        SET status         = @status,
            gate_passed    = @gate_passed,
            latest_run_id  = @run_id,
            run_count      = run_count + 1,
            updated_at     = CURRENT_TIMESTAMP()
        WHERE experiment_id = @config_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("status",      "STRING",  status),
            bigquery.ScalarQueryParameter("gate_passed", "BOOL",    gate_passed),
            bigquery.ScalarQueryParameter("run_id",      "STRING",  run_id),
            bigquery.ScalarQueryParameter("config_id",   "STRING",  experiment_config_id),
        ]
    )
    client.query(ddl, job_config=job_config).result()
    logger.info(
        f"experiment_configs: status → {status}, gate_passed={gate_passed}, "
        f"latest_run_id={run_id}"
    )


def _run_dml(client: bigquery.Client, ddl: str, experiment_config_id: str) -> None:
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("config_id", "STRING", experiment_config_id)
        ]
    )
    client.query(ddl, job_config=job_config).result()


# ── Feature matrix construction ───────────────────────────────────────────────

def _build_all_curated_team_features(
    plays: pd.DataFrame,
    games: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute the full set of 23 per-team curated features and merge them into
    a single (team, season, week) DataFrame.
    """
    base_features = compute_season_to_date_features(plays)
    addl_features = compute_additional_team_features(plays)
    situ_features = compute_situational_features(games)

    team_features = base_features.merge(
        addl_features[["team", "season", "week"] + ALL_ADDITIONAL_TEAM_FEATURES],
        on=["team", "season", "week"],
        how="left",
    )
    team_features = team_features.merge(
        situ_features[["team", "season", "week"] + SITUATIONAL_TEAM_FEATURES],
        on=["team", "season", "week"],
        how="left",
    )
    return team_features


def _resolve_dataset_join_info(
    client: bigquery.Client,
    dataset_id: str,
) -> tuple[str, dict[str, str]]:
    """
    Returns (join_key_type, join_key_columns) from platform.datasets.

    join_key_columns maps semantic names → actual column names in the BQ table.
    E.g. {"team": "team_name", "season": "year", "week": "week_number"}

    Falls back to type='team_season_week' and identity mapping if row not found
    or join_key_columns is missing/empty.
    """
    query = f"""
        SELECT join_key_type, join_key_columns
        FROM `{DATASETS_TABLE}`
        WHERE dataset_id = @dataset_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("dataset_id", "STRING", dataset_id)
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())

    if not rows:
        logger.warning(
            f"join_key info not found for dataset_id={dataset_id!r}; "
            "defaulting to team_season_week with identity column mapping"
        )
        return "team_season_week", {{}}

    row = dict(rows[0])
    jkt = row.get("join_key_type") or "team_season_week"

    raw_jkc = row.get("join_key_columns")
    if isinstance(raw_jkc, str):
        try:
            import json
            jkc = json.loads(raw_jkc)
        except Exception:
            jkc = {{}}
    elif isinstance(raw_jkc, dict):
        jkc = raw_jkc
    else:
        jkc = {{}}

    return jkt, jkc


def _join_user_dataset(
    client: bigquery.Client,
    game_features: pd.DataFrame,
    dataset_id: str,
    columns: list[dict],  # list of {column, semantic_name} dicts from config
) -> pd.DataFrame:
    """
    Fetch user_datasets.{dataset_id} from BigQuery, determine join key type,
    then left-join the selected columns into game_features.

    For game_id join keys: one row per game — joined directly on game_id.
      The feature is a single game-level value; no home/away prefix is added.

    For team_season_week join keys: one row per team per week — joined twice
      (once for home team, once for away team) and prefixed home_/away_.
      Null values for missing rows are filled with 0.

    Returns the augmented game_features DataFrame.
    """
    raw_col_names  = [c["column"]        for c in columns]
    semantic_names = [c["semantic_name"] for c in columns]
    col_rename     = dict(zip(raw_col_names, semantic_names))

    join_key_type, join_key_columns = _resolve_dataset_join_info(client, dataset_id)
    bq_table       = f"`{PROJECT}.user_datasets.{dataset_id}`"

    if join_key_type == "game_id":
        # ── Game-level join ───────────────────────────────────────────────────
        actual_game_id_col = join_key_columns.get("game_id", "game_id")
        col_select = ", ".join(
            f"`{c}`" for c in [actual_game_id_col] + raw_col_names
        )
        query = f"SELECT {col_select} FROM {bq_table}"
        ud_df = client.query(query).to_dataframe()
        if actual_game_id_col != "game_id":
            ud_df = ud_df.rename(columns={actual_game_id_col: "game_id"})
        ud_df = ud_df.rename(columns=col_rename)

        game_features = game_features.merge(
            ud_df[["game_id"] + semantic_names],
            on="game_id",
            how="left",
        )
        for sname in semantic_names:
            if game_features[sname].dtype.kind in ("f", "i"):
                game_features[sname] = game_features[sname].fillna(0)

    elif join_key_type in ("team_season_week", "player_season_week"):
        # ── Team-level join — join twice for home and away ────────────────────
        actual_team_col   = join_key_columns.get("team",   "team")
        actual_season_col = join_key_columns.get("season", "season")
        actual_week_col   = join_key_columns.get("week",   "week")
        actual_join_cols  = [actual_team_col, actual_season_col, actual_week_col]
        col_select = ", ".join(f"`{c}`" for c in actual_join_cols + raw_col_names)
        query = f"SELECT {col_select} FROM {bq_table}"
        ud_df = client.query(query).to_dataframe()
        # Normalise to semantic join column names so the merge always works
        ud_df = ud_df.rename(columns={
            actual_team_col:   "team",
            actual_season_col: "season",
            actual_week_col:   "week",
        })
        ud_df = ud_df.rename(columns=col_rename)

        for prefix, team_col in [("home", "home_team"), ("away", "away_team")]:
            ud_prefixed = (
                ud_df[["team", "season", "week"] + semantic_names]
                .rename(columns={"team": team_col} | {s: f"{prefix}_{s}" for s in semantic_names})
            )
            game_features = game_features.merge(
                ud_prefixed, on=[team_col, "season", "week"], how="left"
            )
            for s in semantic_names:
                col = f"{prefix}_{s}"
                if col in game_features and game_features[col].dtype.kind in ("f", "i", "u"):
                    game_features[col] = game_features[col].fillna(0)
    else:
        logger.warning(
            f"Unrecognised join_key_type={join_key_type!r} for dataset "
            f"{dataset_id!r}; skipping join."
        )

    logger.info(
        f"Joined user dataset {dataset_id!r} "
        f"(join_key={join_key_type}, actual_cols={join_key_columns}, feature_cols={semantic_names})"
    )
    return game_features


def build_feature_matrix(
    client: bigquery.Client,
    plays: pd.DataFrame,
    games: pd.DataFrame,
    config_features: list[dict],
) -> tuple[pd.DataFrame, list[str]]:
    """
    Build the game-level feature matrix according to the config feature list.

    config_features is the parsed ``features`` JSON from experiment_configs:
        [{"dataset": str, "column": str, "semantic_name": str}, ...]

    Returns
    -------
    game_features   : DataFrame ready for the walk-forward harness
    model_feat_cols : Ordered list of column names to pass as model_features
    """
    # ── 1. Compute all curated team features ─────────────────────────────────
    logger.info("Computing curated team features (all 23 per-team) ...")
    team_features = _build_all_curated_team_features(plays, games)

    # ── 2. Identify which curated per-team features the config requests ───────
    curated_entries  = [f for f in config_features if f["dataset"] == "curated"]
    requested_cols   = [f["column"] for f in curated_entries]

    # Validate requested columns against known catalog
    unknown = [c for c in requested_cols if c not in ALL_CURATED_TEAM_FEATURES]
    if unknown:
        raise ValueError(
            f"Config requests curated features not in the catalog: {unknown}. "
            f"Available: {ALL_CURATED_TEAM_FEATURES}"
        )

    # ── 3. Build game feature matrix for selected curated features ────────────
    logger.info(
        f"Building game feature matrix with {len(requested_cols)} "
        f"per-team curated features ..."
    )
    game_features = build_game_feature_matrix(
        games,
        team_features,
        team_feature_cols=requested_cols,
    )
    game_features = add_rest_differential(game_features)

    # ── 4. Derive model feature column list (home_ + away_ per-team, then context) ──
    model_feat_cols = (
        [f"home_{c}" for c in requested_cols]
        + [f"away_{c}" for c in requested_cols]
        + GAME_CONTEXT_FEATURES
        + ["rest_differential"]
    )

    # ── 5. Join user dataset features ─────────────────────────────────────────
    user_entries: dict[str, list[dict]] = {}
    for f in config_features:
        if f["dataset"] != "curated":
            # dataset field expected to be "user_datasets.{uuid}" or just "{uuid}"
            ds_field   = f["dataset"]
            dataset_id = ds_field.split("user_datasets.")[-1] if "user_datasets." in ds_field else ds_field
            user_entries.setdefault(dataset_id, []).append(
                {"column": f["column"], "semantic_name": f["semantic_name"]}
            )

    for dataset_id, cols in user_entries.items():
        game_features = _join_user_dataset(client, game_features, dataset_id, cols)
        join_key_type, _ = _resolve_dataset_join_info(client, dataset_id)
        if join_key_type == "game_id":
            model_feat_cols += [c["semantic_name"] for c in cols]
        else:
            for c in cols:
                model_feat_cols += [f"home_{c['semantic_name']}", f"away_{c['semantic_name']}"]

    # Verify all expected model feature columns actually exist
    missing_cols = [c for c in model_feat_cols if c not in game_features.columns]
    if missing_cols:
        raise ValueError(
            f"Expected model feature columns missing from game_features: {missing_cols}"
        )

    return game_features, model_feat_cols


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── 0. Read env var ───────────────────────────────────────────────────────
    experiment_config_id = os.environ.get("EXPERIMENT_CONFIG_ID")
    if not experiment_config_id:
        logger.error("EXPERIMENT_CONFIG_ID environment variable is not set.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"Config-driven Experiment Runner")
    logger.info(f"EXPERIMENT_CONFIG_ID = {experiment_config_id}")
    logger.info("=" * 60)

    # ── 1. BigQuery client ────────────────────────────────────────────────────
    try:
        client = bigquery.Client(project=PROJECT)
        client.query("SELECT 1").result()
        logger.info("BigQuery connection OK")
    except Exception as e:
        logger.error(f"BigQuery connection failed: {e}")
        sys.exit(1)

    # ── 2. Load experiment config ─────────────────────────────────────────────
    config = load_experiment_config(client, experiment_config_id)

    methodology  = config["methodology"]
    evaluation   = config["evaluation"]
    model_cfg    = config["model"]

    # Unpack methodology
    start_season  = int(methodology["start_season"])
    end_season    = int(methodology["end_season"])
    train_seasons = int(methodology["train_seasons"])
    test_seasons  = int(methodology.get("test_seasons", 1))

    # Unpack evaluation / gate thresholds
    gate_hit_rate  = float(evaluation.get("success_threshold", PHASE2_GATE_HIT_RATE))
    gate_min_games = int(evaluation.get("min_sample", PHASE2_GATE_MIN_GAMES))

    # Resolve model class
    model_type  = model_cfg.get("type", "xgboost")
    model_class = MODEL_REGISTRY.get(model_type)
    if model_class is None:
        raise ValueError(
            f"Unknown model type {model_type!r}. "
            f"Available: {list(MODEL_REGISTRY.keys())}"
        )

    # Build fold list from config parameters
    folds = build_folds_from_config(
        start_season=start_season,
        end_season=end_season,
        train_seasons=train_seasons,
        test_seasons=test_seasons,
    )
    logger.info(
        f"Fold structure: {len(folds)} folds, "
        f"train_seasons={train_seasons}, test_seasons={test_seasons}, "
        f"range {start_season}–{end_season}"
    )

    # Use NFL_RUN_ID from the API if available (so the run is linked to the
    # pre-generated UUID the caller knows about).  Fall back to a locally
    # generated ID for local/test invocations.
    nfl_run_id = os.environ.get("NFL_RUN_ID")
    run_id = nfl_run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + "_" + uuid.uuid4().hex[:6]
    )
    logger.info(f"Run ID: {run_id} (from NFL_RUN_ID env: {bool(nfl_run_id)})")

    # Mark config as running
    _set_config_running(client, experiment_config_id)

    # ── Vars updated in the try block, read in finally ─────────────────────
    result     = None
    gate_passed = False
    error_msg: Optional[str] = None
    completed_at: Optional[datetime] = None

    try:
        # ── 3. Load data ──────────────────────────────────────────────────────
        logger.info("Loading curated data ...")
        plays = load_plays(client)
        games = load_games(client)

        assert len(plays) > 400_000, f"Unexpected play count: {len(plays)}"
        assert len(games) > 2_800,   f"Unexpected game count: {len(games)}"
        logger.info(f"Loaded {len(plays):,} plays, {len(games):,} games")

        # ── 4. Build feature matrix ───────────────────────────────────────────
        game_features, model_feat_cols = build_feature_matrix(
            client, plays, games, config["features"]
        )
        logger.info(
            f"Feature matrix built: {len(game_features):,} games, "
            f"{len(model_feat_cols)} model features"
        )

        # ── 5. Walk-forward backtest ──────────────────────────────────────────
        result = run_walk_forward(
            game_features=game_features,
            experiment_id=run_id,
            name=config["name"],
            model_features=model_feat_cols,
            model_class=model_class,
            folds_override=folds,
            gate_hit_rate=gate_hit_rate,
            gate_min_games=gate_min_games,
        )
        gate_passed = result.gate_passed

        # ── 6. Write results to BigQuery ──────────────────────────────────────
        logger.info("Writing results to BigQuery ...")
        setup_experiments_tables(client)

        completed_at = datetime.now(timezone.utc)

        write_backtest_run(
            client,
            result,
            model_feat_cols,
            notes=config.get("description") or "",
            training_window_years=train_seasons,
            run_id=run_id,
            experiment_config_id=experiment_config_id,
            success_criteria=evaluation,
            folds_complete=len(folds),
            folds_total=len(folds),
            completed_at=completed_at,
            error_message=None,
            feature_importances=result.feature_importance_dict,
        )
        write_backtest_predictions(
            client,
            result,
            run_id=run_id,
            experiment_config_id=experiment_config_id,
        )
        logger.info("BigQuery writes complete")

        # ── 7. Write local artifacts ──────────────────────────────────────────
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        report_path = REPORTS_DIR / f"{run_id}_report.md"
        report_path.write_text(format_backtest_report(result), encoding="utf-8")
        logger.info(f"Report: {report_path}")

        fi_path = REPORTS_DIR / f"{run_id}_feature_importance.json"
        if result.avg_feature_importance is not None:
            fi_path.write_text(
                result.avg_feature_importance.to_json(orient="records", indent=2),
                encoding="utf-8",
            )

        preds_path = REPORTS_DIR / f"{run_id}_predictions.csv"
        result.all_predictions().to_csv(preds_path, index=False)

        season_path = REPORTS_DIR / f"{run_id}_by_season.csv"
        result.per_season_table().to_csv(season_path, index=False)

        # ── Print summary ─────────────────────────────────────────────────────
        gate_str = "PASSED" if gate_passed else "NOT MET"
        print("")
        print("=" * 60)
        print(f"CONFIG-DRIVEN BACKTEST COMPLETE  ({config['name']})")
        print("=" * 60)
        print(f"Experiment Config ID : {experiment_config_id}")
        print(f"Run ID               : {run_id}")
        print(f"Model                : {model_type}")
        print(f"Features             : {len(model_feat_cols)}")
        print(f"Folds                : {len(folds)}")
        print(f"Overall ATS          : {result.total_wins}-{result.total_losses}-{result.total_pushes}")
        print(f"Hit rate             : {result.overall_hit_rate:.3%}  ({result.total_n_games} games)")
        print(f"Gate ({gate_hit_rate:.0%}/{gate_min_games}+ games) : {gate_str}")
        print("=" * 60)

    except Exception as exc:
        error_msg = str(exc)
        logger.exception(f"Backtest failed: {exc}")
        raise

    finally:
        # ── Always update experiment_configs, even on failure ─────────────────
        try:
            _set_config_done(
                client,
                experiment_config_id,
                run_id=run_id,
                gate_passed=gate_passed,
                error_message=error_msg,
            )
        except Exception as update_exc:
            logger.error(
                f"Failed to update experiment_configs status: {update_exc}. "
                "Manual cleanup may be required."
            )


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────────────────────
# AMBIGUITIES FOUND — for PROJECT-LEAD review before BACKEND-API swaps stub
# ─────────────────────────────────────────────────────────────────────────────
#
# 1. GAME-CONTEXT FEATURES NOT IN CONFIG FEATURE LIST
#    The config's ``features`` array describes per-team features only.
#    This runner always appends the 5 game-context columns
#    (home_advantage, div_game, roof_dome, temp, wind) plus rest_differential
#    to the model feature list, matching Phase 1 behaviour.  If the UI
#    intends for the user to opt-in/out of game-context features, the
#    ``features`` schema and this runner both need updating.
#
# 2. methodology.train_seasons AND test_seasons ARE COUNTS, NOT LISTS
#    The schema says ``methodology`` is ``{type, train_seasons, test_seasons,
#    start_season, end_season}``.  This runner treats train_seasons and
#    test_seasons as *integers* (number of seasons), not lists.  The fold
#    derivation: starting at start_season + train_seasons, advance by
#    test_seasons until end_season.  Confirm this matches what the UI stores.
#
# 3. model.type MUST MATCH MODEL_REGISTRY
#    Valid values: "ol_xgb_v1", "ol_xgb_v2".  Any other string raises
#    ValueError before the run starts.  BACKEND-API should validate against
#    this list at config-save time to fail early.
#
# 4. USER DATASET COLUMN NAMING CONVENTION
#    For team_season_week datasets the user data table must have columns
#    named exactly "team", "season", "week".  For game_id datasets it must
#    have a "game_id" column.  The join silently produces all-null columns
#    if the naming convention differs.  BACKEND-API should enforce this at
#    upload/mapping time.
#
# 5. evaluation.metric IS NOT YET USED
#    The config stores ``evaluation.metric`` (e.g., "ats_hit_rate") but this
#    runner always evaluates on ATS hit rate regardless.  For Phase 2 this is
#    fine (all experiments use ATS), but will need wiring when "total_over"
#    or "team_total_yards" targets are supported.
#
# 6. experiment_config_id / success_criteria ALREADY IN LIVE TABLE
#    DATA-PIPELINE's migrate_phase2.py added these two columns to
#    experiments.backtest_runs on 2026-05-04.  This runner writes to them
#    correctly.  The four additional Phase 2 columns (folds_complete,
#    folds_total, completed_at, error_message) did NOT exist before — they
#    are added by _alter_runs_table_phase2() inside setup_experiments_tables().

"""
Post-hoc experiment analysis script — Phase 4 Track 2 (item 2.3).

CLI
---
    python backtests/analyze_experiment.py --run_id <run_id> [--project nfl-model-471509]

Outputs (written to backtests/reports/)
---------------------------------------
  {run_id}_per_spread_slice.csv       — hit rate by |home_spread_close| bucket
  {run_id}_calibration.csv            — 10-bin calibration (predicted prob vs actual rate)
  {run_id}_permutation_importance.csv — hit-rate drop per feature when permuted in test set

Required BigQuery tables
------------------------
  experiments.backtest_predictions    — per-game predictions
  experiments.backtest_runs           — aggregate run metadata (feature list, config)

For permutation importance the script rebuilds the feature matrix from curated data
and reruns fold-level inference — it does NOT write to BigQuery.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

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
from features.comprehensive import compute_additional_team_features, ALL_ADDITIONAL_TEAM_FEATURES
from features.situational import compute_situational_features, add_rest_differential, SITUATIONAL_TEAM_FEATURES
from backtests.walk_forward import build_folds_from_config
from models.xgb_v2 import OLXGBModelV2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT     = "nfl-model-471509"
REPORTS_DIR = ROOT / "backtests" / "reports"

PREDS_TABLE = f"{PROJECT}.experiments.backtest_predictions"
RUNS_TABLE  = f"{PROJECT}.experiments.backtest_runs"


# ── Data loaders ─────────────────────────────────────────────────────────────

def _load_predictions(client: bigquery.Client, run_id: str) -> pd.DataFrame:
    query = f"""
        SELECT
            game_id, season, week, home_team, away_team,
            home_spread_close,
            predicted_home_cover_prob,
            predicted_side,
            actual_home_covered,
            correct,
            fold
        FROM `{PREDS_TABLE}`
        WHERE run_id = @run_id
        ORDER BY season, week, game_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    )
    df = client.query(query, job_config=job_config).to_dataframe()
    if df.empty:
        raise ValueError(f"No predictions found for run_id={run_id!r}")
    logger.info(f"Loaded {len(df):,} predictions for run_id={run_id}")
    return df


def _load_run_meta(client: bigquery.Client, run_id: str) -> dict:
    query = f"""
        SELECT features, ats_hit_rate, n_games_evaluated, gate_passed,
               training_window_years, seasons_evaluated
        FROM `{RUNS_TABLE}`
        WHERE run_id = @run_id
        ORDER BY run_at DESC
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    )
    rows = list(client.query(query, job_config=job_config).result())
    if not rows:
        raise ValueError(f"No backtest_runs row found for run_id={run_id!r}")
    row = dict(rows[0])
    for col in ("features", "seasons_evaluated"):
        if isinstance(row.get(col), str):
            row[col] = json.loads(row[col])
    return row


# ── Analysis A: per-spread-slice ─────────────────────────────────────────────

SPREAD_BINS = [
    ("<=3",    lambda s: s.abs() <= 3),
    ("(3,7]",  lambda s: (s.abs() > 3) & (s.abs() <= 7)),
    ("(7,10]", lambda s: (s.abs() > 7) & (s.abs() <= 10)),
    (">10",    lambda s: s.abs() > 10),
]


def analyze_spread_slices(preds: pd.DataFrame) -> pd.DataFrame:
    """Return hit rate by |home_spread_close| bucket."""
    rows = []
    spread = preds["home_spread_close"].astype(float)
    decided = preds.dropna(subset=["correct"])

    for label, mask_fn in SPREAD_BINS:
        bucket_mask = mask_fn(spread)
        bucket_decided = decided[bucket_mask.reindex(decided.index, fill_value=False)]
        wins   = int(bucket_decided["correct"].sum())
        n      = len(bucket_decided)
        losses = n - wins
        hit    = wins / n if n > 0 else float("nan")
        rows.append({
            "spread_bucket": label,
            "wins":    wins,
            "losses":  losses,
            "n_games": n,
            "hit_rate": round(hit, 4),
        })

    df = pd.DataFrame(rows)
    logger.info(f"Spread slices:\n{df.to_string(index=False)}")
    return df


# ── Analysis B: calibration ───────────────────────────────────────────────────

def analyze_calibration(preds: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """10 equal-width bins of predicted_home_cover_prob vs actual cover rate."""
    decided = preds.dropna(subset=["correct"]).copy()
    decided["bin"] = pd.cut(
        decided["predicted_home_cover_prob"],
        bins=n_bins,
        labels=False,
        include_lowest=True,
    )
    bins_info = pd.cut(
        decided["predicted_home_cover_prob"],
        bins=n_bins,
        include_lowest=True,
    )
    decided["bin_label"] = bins_info.astype(str)

    out = (
        decided.groupby("bin", observed=False)
        .agg(
            bin_label   =("bin_label", "first"),
            n_games     =("correct",   "count"),
            actual_rate =("correct",   "mean"),
            mean_pred   =("predicted_home_cover_prob", "mean"),
        )
        .reset_index(drop=True)
    )
    out["actual_rate"] = out["actual_rate"].round(4)
    out["mean_pred"]   = out["mean_pred"].round(4)
    logger.info(f"Calibration table ({n_bins} bins) computed, {len(out)} non-empty bins")
    return out


# ── Analysis C: permutation importance ───────────────────────────────────────

def _rebuild_feature_matrix(
    client: bigquery.Client,
    feature_cols_base: list[str],
    folds: list[tuple],
) -> tuple[pd.DataFrame, list[str]]:
    """Rebuild the game feature matrix used during the experiment."""
    plays = load_plays(client)
    games = load_games(client)

    base_features = compute_season_to_date_features(plays)
    addl_features = compute_additional_team_features(plays)
    situ_features = compute_situational_features(games)

    ALL_CURATED = ALL_TEAM_RATE_FEATURES + ALL_ADDITIONAL_TEAM_FEATURES + SITUATIONAL_TEAM_FEATURES

    team_features = base_features.merge(
        addl_features[["team", "season", "week"] + ALL_ADDITIONAL_TEAM_FEATURES],
        on=["team", "season", "week"], how="left",
    ).merge(
        situ_features[["team", "season", "week"] + SITUATIONAL_TEAM_FEATURES],
        on=["team", "season", "week"], how="left",
    )

    matrix_cols = list(dict.fromkeys(feature_cols_base + ["rest_days"]))
    game_features = build_game_feature_matrix(games, team_features, team_feature_cols=matrix_cols)
    game_features = add_rest_differential(game_features)

    model_feat_cols = (
        [f"home_{c}" for c in feature_cols_base]
        + [f"away_{c}" for c in feature_cols_base]
        + GAME_CONTEXT_FEATURES
        + ["rest_differential"]
    )

    missing = [c for c in model_feat_cols if c not in game_features.columns]
    if missing:
        raise ValueError(f"Feature matrix missing columns: {missing}")

    return game_features, model_feat_cols


def _run_fold_inference(
    game_features: pd.DataFrame,
    model_feat_cols: list[str],
    folds: list[tuple],
    permute_col: str | None = None,
    seed: int = 42,
) -> float:
    """
    Run walk-forward inference (fit+predict) over folds. If permute_col is not
    None, randomly permute that column in the TEST set only (per fold).

    Returns overall ATS hit rate.
    """
    rng = np.random.default_rng(seed)
    all_correct = []

    for train_seasons, test_season in folds:
        train_mask = game_features["season"].isin(train_seasons)
        test_mask  = game_features["season"] == test_season

        train_df = game_features[train_mask].dropna(subset=["home_covered"]).copy()
        test_df  = game_features[test_mask].copy()

        X_train = train_df[model_feat_cols]
        y_train = train_df["home_covered"].astype(int)
        X_test  = test_df[model_feat_cols].copy()

        if permute_col is not None and permute_col in X_test.columns:
            X_test[permute_col] = rng.permutation(X_test[permute_col].values)

        model = OLXGBModelV2(random_seed=42)
        model.fit(X_train, y_train)
        probs = model.predict_proba(X_test)

        pred_home = probs > 0.5
        actual    = test_df["home_covered"].values

        for pred, act in zip(pred_home, actual):
            if act is None or (isinstance(act, float) and np.isnan(act)):
                continue
            all_correct.append(int(pred == bool(act)))

    n = len(all_correct)
    return sum(all_correct) / n if n > 0 else float("nan")


def analyze_permutation_importance(
    client: bigquery.Client,
    run_meta: dict,
    folds: list[tuple],
) -> pd.DataFrame:
    """Measure hit-rate drop when each feature column is permuted in the test set."""
    # Determine base feature names from the stored feature list
    raw_features = run_meta.get("features") or []
    if isinstance(raw_features, str):
        raw_features = json.loads(raw_features)

    # The stored features list contains home_/away_ prefixed names; extract base names
    seen: set[str] = set()
    base_cols: list[str] = []

    ALL_CURATED = ALL_TEAM_RATE_FEATURES + ALL_ADDITIONAL_TEAM_FEATURES + SITUATIONAL_TEAM_FEATURES

    for col in raw_features:
        base = col
        for pfx in ("home_", "away_"):
            if col.startswith(pfx):
                base = col[len(pfx):]
                break
        if base in ALL_CURATED and base not in seen:
            seen.add(base)
            base_cols.append(base)

    logger.info(f"Rebuilding feature matrix for permutation importance ({len(base_cols)} base features) ...")
    game_features, model_feat_cols = _rebuild_feature_matrix(client, base_cols, folds)

    logger.info("Running baseline inference ...")
    baseline_hr = _run_fold_inference(game_features, model_feat_cols, folds, permute_col=None)
    logger.info(f"Baseline hit rate (no permutation): {baseline_hr:.4%}")

    rows = []
    for feat_col in model_feat_cols:
        logger.info(f"Permuting {feat_col} ...")
        permuted_hr = _run_fold_inference(game_features, model_feat_cols, folds, permute_col=feat_col)
        drop = baseline_hr - permuted_hr
        rows.append({
            "feature":        feat_col,
            "baseline_hr":    round(baseline_hr, 4),
            "permuted_hr":    round(permuted_hr, 4),
            "hr_drop":        round(drop, 4),
        })

    df = (
        pd.DataFrame(rows)
        .sort_values("hr_drop", ascending=False)
        .reset_index(drop=True)
    )
    logger.info(f"Permutation importance complete ({len(df)} features)")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Post-hoc analysis for a backtest run")
    parser.add_argument("--run_id",   required=True, help="run_id from experiments.backtest_runs")
    parser.add_argument("--project",  default=PROJECT, help="GCP project")
    parser.add_argument(
        "--analyses",
        default="spread,calibration,permutation",
        help="Comma-separated list: spread,calibration,permutation",
    )
    args = parser.parse_args()

    analyses = {a.strip() for a in args.analyses.split(",")}

    client = bigquery.Client(project=args.project)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    preds    = _load_predictions(client, args.run_id)
    run_meta = _load_run_meta(client, args.run_id)

    # ── Spread slice ─────────────────────────────────────────────────────────
    if "spread" in analyses:
        spread_df = analyze_spread_slices(preds)
        out_path = REPORTS_DIR / f"{args.run_id}_per_spread_slice.csv"
        spread_df.to_csv(out_path, index=False)
        logger.info(f"Wrote: {out_path}")

    # ── Calibration ──────────────────────────────────────────────────────────
    if "calibration" in analyses:
        cal_df = analyze_calibration(preds)
        out_path = REPORTS_DIR / f"{args.run_id}_calibration.csv"
        cal_df.to_csv(out_path, index=False)
        logger.info(f"Wrote: {out_path}")

    # ── Permutation importance ────────────────────────────────────────────────
    if "permutation" in analyses:
        # Reconstruct fold list from run metadata
        seasons_evaluated = run_meta.get("seasons_evaluated") or []
        train_window      = int(run_meta.get("training_window_years") or 4)

        if seasons_evaluated:
            seasons_evaluated = sorted(seasons_evaluated)
            start_season = min(seasons_evaluated) - train_window
            end_season   = max(seasons_evaluated)
            folds = build_folds_from_config(
                start_season=start_season,
                end_season=end_season,
                train_seasons=train_window,
                test_seasons=1,
            )
        else:
            raise ValueError(
                "Cannot reconstruct folds: seasons_evaluated missing from run metadata."
            )

        perm_df = analyze_permutation_importance(client, run_meta, folds)
        out_path = REPORTS_DIR / f"{args.run_id}_permutation_importance.csv"
        perm_df.to_csv(out_path, index=False)
        logger.info(f"Wrote: {out_path}")

    print(f"\nAnalysis complete. Outputs in: {REPORTS_DIR}")


if __name__ == "__main__":
    main()

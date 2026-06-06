"""
Situational Filtering Experiment Runner — Phase 4, Track 5.

Runs sit_div (divisional games) and sit_late (weeks 15+) experiments
using the v2 feature set (23 curated per-team features) with the
game_universe filter applied after building the full feature matrix.

Results are written locally to backtests/reports/ only (no BQ write).

Usage:
    cd 02-MODELING
    python backtests/run_situational.py --experiment sit_div
    python backtests/run_situational.py --experiment sit_late
    python backtests/run_situational.py --experiment both   (default)
"""

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

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
from models.xgb_v2 import OLXGBModelV2

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PROJECT     = "nfl-model-471509"
REPORTS_DIR = ROOT / "backtests" / "reports"

# ── v2 Feature set (same as experiment 20260517_020202_0504ff) ─────────────────
# 23 per-team curated features:
ALL_CURATED_TEAM_FEATURES = (
    ALL_TEAM_RATE_FEATURES           # 12 OL + defense features
    + ALL_ADDITIONAL_TEAM_FEATURES   # 8 comprehensive features
    + SITUATIONAL_TEAM_FEATURES      # 3 situational features
)

# Full model feature list: home_ + away_ per-team, plus game context + rest_diff
V2_MODEL_FEATURES = (
    [f"home_{f}" for f in ALL_CURATED_TEAM_FEATURES]
    + [f"away_{f}" for f in ALL_CURATED_TEAM_FEATURES]
    + GAME_CONTEXT_FEATURES
    + ["rest_differential"]
)

# Walk-forward methodology: 2015-2025, 4-season training windows, 1 test season
METHODOLOGY = {
    "start_season":  2015,
    "end_season":    2025,
    "train_seasons": 4,
    "test_seasons":  1,
    "random_seed":   42,
}

# Experiment configs
EXPERIMENTS = {
    "sit_div": {
        "name":        "sit_div",
        "description": "Divisional games only — v2 feature set. Phase 4 Track 5.",
        "universe":    {"field": "div_game", "operator": "eq", "value": 1},  # div_game cast to int in build_game_feature_matrix
    },
    "sit_late": {
        "name":        "sit_late",
        "description": "Late-season games (week >= 15) — v2 feature set. Phase 4 Track 5.",
        "universe":    {"field": "week", "operator": "gte", "value": 15},
    },
}


def apply_universe_filter(game_features, universe: dict):
    """Apply a game_universe filter to game_features. Returns filtered DataFrame."""
    field    = universe["field"]
    operator = universe.get("operator", "eq")
    value    = universe["value"]

    if field not in game_features.columns:
        raise ValueError(
            f"game_universe filter field {field!r} not found in game_features columns. "
            f"Available: {list(game_features.columns)}"
        )

    before = len(game_features)

    if operator == "eq":
        filtered = game_features[game_features[field] == value].copy()
    elif operator == "gte":
        filtered = game_features[game_features[field] >= value].copy()
    elif operator == "lte":
        filtered = game_features[game_features[field] <= value].copy()
    elif operator == "ne":
        filtered = game_features[game_features[field] != value].copy()
    else:
        raise ValueError(
            f"Unsupported operator {operator!r}. Supported: eq, gte, lte, ne"
        )

    after = len(filtered)
    logger.info(
        f"Universe filter: {field} {operator} {value!r}  "
        f"{before:,} -> {after:,} games ({before - after:,} excluded)"
    )

    if after < 100:
        raise ValueError(
            f"Universe filter left only {after} games — too few to run a "
            "meaningful backtest."
        )

    return filtered


def build_full_game_features(client):
    """Load data and build the full (unfiltered) v2 feature matrix."""
    logger.info("Loading curated data ...")
    plays = load_plays(client)
    games = load_games(client)

    assert len(plays) > 400_000, f"Unexpected play count: {len(plays)}"
    assert len(games) > 2_800,   f"Unexpected game count: {len(games)}"
    logger.info(f"Loaded {len(plays):,} plays, {len(games):,} games")

    logger.info("Computing curated team features (all 23 per-team) ...")
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

    logger.info("Building game feature matrix ...")
    game_features = build_game_feature_matrix(
        games,
        team_features,
        team_feature_cols=ALL_CURATED_TEAM_FEATURES,
    )
    game_features = add_rest_differential(game_features)

    logger.info(
        f"Feature matrix built: {len(game_features):,} games, "
        f"{len(V2_MODEL_FEATURES)} model features"
    )
    return game_features


def run_situational_experiment(experiment_name: str, game_features, folds):
    """Apply universe filter and run walk-forward for one experiment."""
    exp_cfg = EXPERIMENTS[experiment_name]
    logger.info("=" * 60)
    logger.info(f"Starting experiment: {exp_cfg['name']}")
    logger.info(f"Universe: {exp_cfg['universe']}")
    logger.info("=" * 60)

    filtered = apply_universe_filter(game_features, exp_cfg["universe"])

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + "_" + uuid.uuid4().hex[:6]
    )
    logger.info(f"Run ID: {run_id}")

    result = run_walk_forward(
        game_features=filtered,
        experiment_id=run_id,
        name=exp_cfg["name"],
        model_features=V2_MODEL_FEATURES,
        model_class=OLXGBModelV2,
        folds_override=folds,
        gate_hit_rate=PHASE2_GATE_HIT_RATE,
        gate_min_games=PHASE2_GATE_MIN_GAMES,
        random_seed=METHODOLOGY["random_seed"],
    )

    return result, run_id, exp_cfg


def save_results(result, run_id: str, exp_cfg: dict):
    """Write local artifacts: predictions CSV, by-season CSV, markdown report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    preds_path  = REPORTS_DIR / f"{run_id}_{exp_cfg['name']}_predictions.csv"
    season_path = REPORTS_DIR / f"{run_id}_{exp_cfg['name']}_by_season.csv"
    report_path = REPORTS_DIR / f"{run_id}_{exp_cfg['name']}_report.md"
    fi_path     = REPORTS_DIR / f"{run_id}_{exp_cfg['name']}_feature_importance.json"

    result.all_predictions().to_csv(preds_path, index=False)
    logger.info(f"Predictions: {preds_path}")

    result.per_season_table().to_csv(season_path, index=False)
    logger.info(f"Season breakdown: {season_path}")

    # Write extended markdown report
    report_lines = []
    report_lines.append(f"# Situational Experiment Report — {exp_cfg['name']}")
    report_lines.append("")
    report_lines.append(f"**Run ID:** `{run_id}`")
    report_lines.append(f"**Experiment:** {exp_cfg['name']}")
    report_lines.append(f"**Description:** {exp_cfg['description']}")
    universe = exp_cfg["universe"]
    report_lines.append(
        f"**Universe filter:** `{universe['field']} {universe.get('operator','eq')} {universe['value']}`"
    )
    report_lines.append(f"**Feature set:** v2 — {len(V2_MODEL_FEATURES)} features "
                        f"({len(ALL_CURATED_TEAM_FEATURES)} per-team x2 + game context + rest_diff)")
    report_lines.append(f"**Walk-forward:** 2015–2025, 4-season training, 1-season test")
    report_lines.append(f"**Gate:** >=54% hit rate on >=250 games")
    report_lines.append("")

    report_lines.append("## Primary Result")
    report_lines.append("")
    report_lines.append(
        f"**Overall ATS:** {result.total_wins}-{result.total_losses}-{result.total_pushes}"
    )
    report_lines.append(
        f"**Hit rate:** {result.overall_hit_rate:.3%} ({result.total_n_games} decided games)"
    )
    gate_str = "YES — GATE PASSED" if result.gate_passed else "NO — gate not met"
    report_lines.append(f"**Gate (>=54%, >=250 games):** {gate_str}")
    report_lines.append(f"**Always-home baseline:** {result.baseline_hit_rate:.3%}")
    report_lines.append("")

    report_lines.append("## Per-Season Breakdown")
    report_lines.append("")
    report_lines.append("| Season | W | L | P | Hit rate | N games | Log-loss | Baseline |")
    report_lines.append("|--------|---|---|---|----------|---------|----------|----------|")
    for fr in result.folds:
        import numpy as np
        hr  = f"{fr.hit_rate:.3%}"   if not (fr.hit_rate != fr.hit_rate)   else "--"
        ll  = f"{fr.model_log_loss:.4f}" if not (fr.model_log_loss != fr.model_log_loss) else "--"
        bhr = f"{fr.baseline_hit_rate:.3%}" if not (fr.baseline_hit_rate != fr.baseline_hit_rate) else "--"
        report_lines.append(
            f"| {fr.test_season} | {fr.wins} | {fr.losses} | {fr.pushes} "
            f"| {hr} | {fr.n_games} | {ll} | {bhr} |"
        )
    report_lines.append("")

    if result.avg_feature_importance is not None:
        report_lines.append("## Top 10 Features by Mean Importance")
        report_lines.append("")
        report_lines.append("| Rank | Feature | Mean Importance |")
        report_lines.append("|------|---------|-----------------|")
        fi_top = result.avg_feature_importance.head(10)
        for rank, row in enumerate(fi_top.itertuples(), 1):
            report_lines.append(f"| {rank} | {row.feature} | {row.importance:.4f} |")
        report_lines.append("")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info(f"Report: {report_path}")

    if result.avg_feature_importance is not None:
        fi_path.write_text(
            result.avg_feature_importance.to_json(orient="records", indent=2),
            encoding="utf-8",
        )
        logger.info(f"Feature importance: {fi_path}")

    return preds_path, season_path, report_path


def print_summary(result, run_id: str, exp_cfg: dict):
    """Print ASCII summary to stdout."""
    gate_str = "PASSED" if result.gate_passed else "NOT MET"
    print("")
    print("=" * 60)
    print(f"SITUATIONAL EXPERIMENT: {exp_cfg['name'].upper()}")
    print("=" * 60)
    print(f"Run ID       : {run_id}")
    universe = exp_cfg["universe"]
    print(f"Universe     : {universe['field']} {universe.get('operator','eq')} {universe['value']}")
    print(f"Overall ATS  : {result.total_wins}-{result.total_losses}-{result.total_pushes}")
    print(f"Hit rate     : {result.overall_hit_rate:.3%}  ({result.total_n_games} games)")
    print(f"Baseline     : {result.baseline_hit_rate:.3%}")
    print(f"Gate (>=54%, >=250 games): {gate_str}")
    print("")
    print("Per-fold breakdown:")
    folds_above_54 = 0
    for fr in result.folds:
        hr = f"{fr.hit_rate:.3%}" if fr.hit_rate == fr.hit_rate else "--"
        flag = " <-- above 54%" if fr.hit_rate >= 0.54 else ""
        if fr.hit_rate >= 0.54:
            folds_above_54 += 1
        print(f"  {fr.test_season}: {fr.wins}-{fr.losses}-{fr.pushes}  {hr}  ({fr.n_games} games){flag}")
    print("")
    print(f"Folds above 54%: {folds_above_54}/{len(result.folds)}")

    if result.avg_feature_importance is not None:
        print("")
        print("Top 5 features:")
        for i, row in enumerate(result.avg_feature_importance.head(5).itertuples(), 1):
            print(f"  {i}. {row.feature:50s}  {row.importance:.4f}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Situational Filtering Experiments")
    parser.add_argument(
        "--experiment",
        choices=["sit_div", "sit_late", "both"],
        default="both",
        help="Which experiment to run (default: both)",
    )
    args = parser.parse_args()

    experiments_to_run = (
        ["sit_div", "sit_late"] if args.experiment == "both" else [args.experiment]
    )

    # ── BigQuery client ────────────────────────────────────────────────────────
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=PROJECT)
        client.query("SELECT 1").result()
        logger.info("BigQuery connection OK")
    except Exception as e:
        logger.error(f"BigQuery connection failed: {e}")
        sys.exit(1)

    # ── Build full feature matrix once (expensive — reused for both experiments) ─
    game_features = build_full_game_features(client)

    # ── Build folds ────────────────────────────────────────────────────────────
    folds = build_folds_from_config(
        start_season=METHODOLOGY["start_season"],
        end_season=METHODOLOGY["end_season"],
        train_seasons=METHODOLOGY["train_seasons"],
        test_seasons=METHODOLOGY["test_seasons"],
    )
    logger.info(f"Walk-forward: {len(folds)} folds ({folds[0][0][0]}-{folds[-1][1]})")

    # ── Run experiments ────────────────────────────────────────────────────────
    for exp_name in experiments_to_run:
        try:
            result, run_id, exp_cfg = run_situational_experiment(exp_name, game_features, folds)
            save_results(result, run_id, exp_cfg)
            print_summary(result, run_id, exp_cfg)
        except Exception as e:
            logger.error(f"Experiment {exp_name} failed: {e}")
            import traceback
            traceback.print_exc()

    logger.info("All experiments complete.")


if __name__ == "__main__":
    main()

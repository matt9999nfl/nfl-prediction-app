"""
Phase 1 Backtest — main entry point (ol_xgb_v2, comprehensive feature set).

Run this script from the 02-MODELING directory:

    cd 02-MODELING
    python backtests/run_phase1_backtest.py

What it does (in order):
  1.  Verify BigQuery access
  2.  Load curated.plays and curated.games
  3.  Compute season-to-date OL + defensive features per team per week (v1 base)
  4.  Compute additional comprehensive features: QB efficiency, explosive rates,
      defensive all-play EPA, rolling 3-week EPA trend
  5.  Compute situational / form features: rest days, prior-week margin, season win %
  6.  Merge all team features into a unified (team, season, week) DataFrame
  7.  Build the game-level feature matrix (home/away features joined + rest_differential)
  8.  Compute OL mismatch flags (approved composite, 2026-05-03)
  9.  Run 6-fold walk-forward backtest using OLXGBModelV2
  10. Write results to experiments.backtest_runs + experiments.backtest_predictions
  11. Write a markdown report + feature importance JSON + predictions CSV to backtests/reports/
  12. Append a summary to experiments/EXPERIMENTS.md

Experiment name: ol_xgb_v2
Previous experiment (ol_xgb_v1) is preserved -- not overwritten.

OL mismatch composite (PROJECT-LEAD approved 2026-05-03):
  Offensive: Z(ol_pass_epa_per_att) - Z(ol_pressure_proxy_rate)
  Defensive: Z(def_pressure_proxy_rate) - Z(def_pass_epa_allowed_per_att)
  Per-season, expanding-window quartile boundaries.
  flag=1: home top-quartile offense vs away bottom-quartile defense
  flag=2: away top-quartile offense vs home bottom-quartile defense (diagnostic)
"""

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup: allow imports from 02-MODELING root ───────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.ol_metrics import (
    load_plays,
    load_games,
    compute_season_to_date_features,
    build_game_feature_matrix,
    ALL_TEAM_RATE_FEATURES,
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
from features.mismatch import compute_ol_mismatch_flag, subset_ats_record
from backtests.walk_forward import run_walk_forward, format_backtest_report
from backtests.bq_writer import setup_experiments_tables, write_backtest_run, write_backtest_predictions
from models.xgb_v2 import OLXGBModelV2

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
EXPERIMENT_NAME = "ol_xgb_v2"
REPORTS_DIR     = ROOT / "backtests" / "reports"
EXPERIMENTS_LOG = ROOT / "experiments" / "EXPERIMENTS.md"

# ── v2 Feature set ────────────────────────────────────────────────────────────
# All per-team features (home_ and away_ prefixes added by build_game_feature_matrix)
V2_ALL_TEAM_RATE_FEATURES = (
    ALL_TEAM_RATE_FEATURES           # v1 base: OL pass/run + defense (12 features)
    + ALL_ADDITIONAL_TEAM_FEATURES   # v2 new: QB, explosive, def comprehensive, rolling trend (8)
    + SITUATIONAL_TEAM_FEATURES      # v2 new: rest_days, prior_week_margin, season_win_pct (3)
)

# Game-level context features (not prefixed)
GAME_CONTEXT_FEATURES = [
    "home_advantage",
    "div_game",
    "roof_dome",
    "temp",
    "wind",
    "rest_differential",   # derived: home_rest_days - away_rest_days
]

# Full model feature list passed to walk_forward harness
V2_ALL_MODEL_FEATURES = (
    [f"home_{f}" for f in V2_ALL_TEAM_RATE_FEATURES]
    + [f"away_{f}" for f in V2_ALL_TEAM_RATE_FEATURES]
    + GAME_CONTEXT_FEATURES
)


def main():
    logger.info("=" * 60)
    logger.info("Phase 1 Backtest (ol_xgb_v2) -- starting")
    logger.info("=" * 60)
    logger.info(f"Total model features: {len(V2_ALL_MODEL_FEATURES)}")

    # ── 1. BigQuery client ────────────────────────────────────────────────
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project="nfl-model-471509")
        client.query("SELECT 1").result()
        logger.info("BigQuery connection OK")
    except Exception as e:
        logger.error(f"BigQuery connection failed: {e}")
        logger.error("Ensure GOOGLE_APPLICATION_CREDENTIALS is set or gcloud auth is active.")
        sys.exit(1)

    # ── 2. Load data ──────────────────────────────────────────────────────
    plays = load_plays(client)
    games = load_games(client)

    assert len(plays) > 400_000, f"Unexpected play count: {len(plays)}"
    assert len(games) > 2_800,   f"Unexpected game count: {len(games)}"
    assert games["home_spread_close"].isna().mean() < 0.05, "Spread null rate too high"
    logger.info(f"Data loaded: {len(plays):,} plays, {len(games):,} games")

    # ── 3. v1 base features (OL pass/run + defense) ───────────────────────
    logger.info("Building v1 base team features (OL + defense) ...")
    base_features = compute_season_to_date_features(plays)

    # ── 4. Additional comprehensive features ──────────────────────────────
    logger.info("Building v2 comprehensive features (QB + explosive + def + trend) ...")
    addl_features = compute_additional_team_features(plays)

    # ── 5. Situational / form features ───────────────────────────────────
    logger.info("Building situational/form features (rest + margin + win pct) ...")
    situ_features = compute_situational_features(games)

    # ── 6. Merge all team features ────────────────────────────────────────
    logger.info("Merging all team features ...")
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
    logger.info(
        f"  Merged: {len(team_features):,} rows, "
        f"{len(V2_ALL_TEAM_RATE_FEATURES)} per-team feature columns"
    )

    # ── 7. Build game feature matrix ──────────────────────────────────────
    logger.info("Building game feature matrix ...")
    game_features = build_game_feature_matrix(
        games,
        team_features,
        team_feature_cols=V2_ALL_TEAM_RATE_FEATURES,
    )

    # rest_differential = home_rest_days - away_rest_days (game-level derived)
    game_features = add_rest_differential(game_features)

    week1_count = (game_features["week"] == 1).sum()
    logger.info(f"  Week-1 games in matrix: {week1_count:,} (using prior-season cold-start features)")

    # ── 8. OL mismatch flags (approved 2026-05-03) ────────────────────────
    logger.info("Computing OL mismatch flags ...")
    game_features = compute_ol_mismatch_flag(game_features)

    # ── 9. Walk-forward backtest ──────────────────────────────────────────
    experiment_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + "_" + uuid.uuid4().hex[:6]
    )
    logger.info(f"Experiment ID: {experiment_id}")

    result = run_walk_forward(
        game_features=game_features,
        experiment_id=experiment_id,
        name=EXPERIMENT_NAME,
        model_features=V2_ALL_MODEL_FEATURES,
        model_class=OLXGBModelV2,
    )

    # ── 10. Write to BigQuery ──────────────────────────────────────────────
    logger.info("Writing results to BigQuery ...")
    try:
        setup_experiments_tables(client)
        write_backtest_run(
            client, result, V2_ALL_MODEL_FEATURES,
            notes=(
                "ol_xgb_v2: comprehensive nflfastR feature set. "
                "Adds QB efficiency (CPOE, EPA under pressure, explosive rate), "
                "defensive all-play EPA + explosive rates, rolling 3-wk EPA trend, "
                "situational (rest days, prior margin, season win pct). "
                "OL mismatch composite approved 2026-05-03."
            ),
        )
        write_backtest_predictions(client, result)
        logger.info("BigQuery writes complete")
    except Exception as e:
        logger.warning(f"BigQuery write failed (results still saved locally): {e}")

    # ── 11. Write local artifacts ──────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report_path = REPORTS_DIR / f"{experiment_id}_report.md"
    report_path.write_text(format_backtest_report(result), encoding="utf-8")
    logger.info(f"Report written: {report_path}")

    fi_path = REPORTS_DIR / f"{experiment_id}_feature_importance.json"
    if result.avg_feature_importance is not None:
        fi_path.write_text(
            result.avg_feature_importance.to_json(orient="records", indent=2),
            encoding="utf-8",
        )
        logger.info(f"Feature importance written: {fi_path}")

    preds_path = REPORTS_DIR / f"{experiment_id}_predictions.csv"
    result.all_predictions().to_csv(preds_path, index=False)
    logger.info(f"Predictions written: {preds_path}")

    season_path = REPORTS_DIR / f"{experiment_id}_by_season.csv"
    result.per_season_table().to_csv(season_path, index=False)
    logger.info(f"Season breakdown written: {season_path}")

    # ── 12. Append to EXPERIMENTS.md ──────────────────────────────────────
    _append_experiment_log(result)

    # ── Summary printout (ASCII-only to avoid cp1252 errors) ──────────────
    all_preds = result.all_predictions()
    sub1 = subset_ats_record(all_preds, flag_value=1)
    sub2 = subset_ats_record(all_preds, flag_value=2)

    gate_str = "PASSED" if result.gate_passed else "NOT MET"

    print("")
    print("=" * 60)
    print("PHASE 1 BACKTEST COMPLETE  (ol_xgb_v2)")
    print("=" * 60)
    print(f"Experiment ID   : {result.experiment_id}")
    print(f"Total features  : {len(V2_ALL_MODEL_FEATURES)}")
    print(f"Overall ATS     : {result.total_wins}-{result.total_losses}-{result.total_pushes}")
    print(f"Hit rate        : {result.overall_hit_rate:.3%}  (over {result.total_n_games} games)")
    print(f"Always-home     : {result.baseline_hit_rate:.3%}")
    print(f"Phase 2 gate    : {gate_str}  (>=54%%, >=250 games)")
    print("")
    sub1_hr = f"{sub1['hit_rate']:.3%}" if sub1["hit_rate"] == sub1["hit_rate"] else "--"
    sub2_hr = f"{sub2['hit_rate']:.3%}" if sub2["hit_rate"] == sub2["hit_rate"] else "--"
    print(f"OL flag=1 subset: {sub1['wins']}-{sub1['losses']}-{sub1['pushes']}  {sub1_hr}  ({sub1['n_games']} games)")
    print(f"OL flag=2 subset: {sub2['wins']}-{sub2['losses']}-{sub2['pushes']}  {sub2_hr}  ({sub2['n_games']} games)")
    print("  (subset diagnostic only -- does not gate Phase 2)")
    print("")
    print(f"Full report     : {report_path}")
    print("=" * 60)


def _append_experiment_log(result) -> None:
    """Append a brief summary to experiments/EXPERIMENTS.md."""
    gate_str = "GATE PASSED" if result.gate_passed else "gate not met"
    entry = f"""
---

## `{result.experiment_id}` -- {result.name}

**Run at:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
**Model:** XGBoost ({result.name}), 6-fold walk-forward 2019-2024
**Features:** {len(V2_ALL_MODEL_FEATURES)} total ({len(V2_ALL_TEAM_RATE_FEATURES)} per-team x2 + game context)

**Overall ATS:** {result.total_wins}-{result.total_losses}-{result.total_pushes}
**Hit rate:** {result.overall_hit_rate:.3%} over {result.total_n_games} games
**Always-home baseline:** {result.baseline_hit_rate:.3%}
**Phase 2 gate:** {gate_str}

**Per-season:**

| Season | W | L | P | Hit rate |
|--------|---|---|---|----------|
"""
    for fr in result.folds:
        hr = f"{fr.hit_rate:.3%}" if fr.hit_rate == fr.hit_rate else "--"
        entry += f"| {fr.test_season} | {fr.wins} | {fr.losses} | {fr.pushes} | {hr} |\n"

    entry += "\n**Notes:** Comprehensive nflfastR feature set (QB + OL + defense + situational).\n"

    existing = EXPERIMENTS_LOG.read_text(encoding="utf-8")
    EXPERIMENTS_LOG.write_text(existing + entry, encoding="utf-8")
    logger.info(f"Experiment log updated: {EXPERIMENTS_LOG}")


if __name__ == "__main__":
    main()

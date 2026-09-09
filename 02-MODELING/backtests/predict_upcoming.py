#!/usr/bin/env python3
"""
Forward prediction for SCHEDULED (unplayed) games.

Why this exists
---------------
`run_experiment.py` / `walk_forward.py` answer "would this have worked?".  They
train on completed seasons and score against known results: training drops rows
where `home_covered` is null, and every metric is computed against an actual
outcome.  Nothing in that path can emit a prediction for a game that has not
been played, which is why `GET /api/v1/predictions` had nothing to serve for
2026 week 1.

This script answers the other question: "what does the model say about the
games coming up?"  It is deliberately a separate entry point rather than a flag
on the runner, so the backtest path is untouched.

The one real obstacle, and how it is solved
-------------------------------------------
`compute_season_to_date_features()` derives its (team, season, week) universe
from the plays table.  An unplayed week has no plays, so it produces no team-week
rows, and `build_game_feature_matrix()`'s left join yields NaN for every feature
on the upcoming slate.  The week-1 cold-start fill cannot help: there is no row
to fill.

Rather than fork the feature builders, this script appends zero-valued
PLACEHOLDER PLAYS for each team on the target slate.  That makes the existing,
tested pipeline generate the team-week rows by itself:

  * the placeholder puts (team, season, week) into the team-week universe;
  * the cumulative step is `cum - current_week`, so the placeholder's own zero
    counts are subtracted straight back out and contribute nothing;
  * no later week exists, so nothing downstream is polluted;
  * for week 1 the existing cold-start fill then substitutes the prior season's
    full-season averages — exactly the treatment week 1 received in every
    backtest the model was validated against.

That last point matters for honesty: for week 1 the model is being asked the
same shape of question it was tested on, not a novel one.

What it writes
--------------
`experiments.backtest_predictions` rows with `actual_home_covered` and `correct`
left NULL.  Both columns are already NULLABLE in PREDS_SCHEMA, so an unplayed
game needs no migration.  They are backfilled by `--grade` once results land.

Usage
-----
    python backtests/predict_upcoming.py --season 2026 --week 1 --dry-run
    python backtests/backtests/predict_upcoming.py --season 2026 --week 1
    python backtests/predict_upcoming.py --season 2026 --week 1 --grade

Requires GCP auth (GOOGLE_APPLICATION_CREDENTIALS or `gcloud auth
application-default login`), same as every other script here.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.ol_metrics import (  # noqa: E402
    load_plays,
    load_games,
    compute_season_to_date_features,
    build_game_feature_matrix,
    ALL_TEAM_RATE_FEATURES,
    GAME_CONTEXT_FEATURES,
)
from features.comprehensive import (  # noqa: E402
    compute_additional_team_features,
    ALL_ADDITIONAL_TEAM_FEATURES,
)
from features.situational import (  # noqa: E402
    compute_situational_features,
    add_rest_differential,
    SITUATIONAL_TEAM_FEATURES,
)
from models.xgb_v2 import OLXGBModelV2  # noqa: E402
from backtests.bq_writer import PREDS_SCHEMA, PREDS_TABLE, RUNS_TABLE  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
CONFIGS_TABLE = f"{PROJECT}.platform.experiment_configs"
REPORTS_DIR = ROOT / "backtests" / "reports"

ALL_CURATED_TEAM_FEATURES: list[str] = (
    ALL_TEAM_RATE_FEATURES
    + ALL_ADDITIONAL_TEAM_FEATURES
    + SITUATIONAL_TEAM_FEATURES
)

# Stable identity for the rolling in-season production model.  Reusing one
# experiment_id across weeks means the serving endpoint has a single thing to
# point at all season, and week-over-week predictions stay comparable.
PRODUCTION_EXPERIMENT_ID = "00000000-0000-4000-8000-00000000f0re"
PRODUCTION_EXPERIMENT_NAME = "production-forward-v2"


# ── Placeholder plays ─────────────────────────────────────────────────────────


def build_placeholder_plays(slate: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """
    One zero-valued pass row and one zero-valued run row per team on the slate.

    Both `posteam` and `defteam` are set to the same team so the row enters the
    offensive and defensive team-week universes together.  Every statistic is
    zero, and the cumulative step subtracts the current week from its own total,
    so these rows change no feature value anywhere — they exist only to make the
    (team, season, week) key present.
    """
    teams = pd.unique(pd.concat([slate["home_team"], slate["away_team"]], ignore_index=True))
    rows = []
    for team in teams:
        for play_type in ("pass", "run"):
            rows.append(
                {
                    "game_id": f"__upcoming__{season}_{week:02d}_{team}_{play_type}",
                    "season": season,
                    "week": week,
                    "posteam": team,
                    "defteam": team,
                    "play_type": play_type,
                    "down": 1,
                    "sack": 0,
                    "qb_hit": 0,
                    "epa": 0.0,
                    "yards_gained": 0,
                    "cpoe": np.nan,
                }
            )
    ph = pd.DataFrame(rows)
    logger.info(
        "Placeholder plays: %d rows for %d teams on the %d week %d slate",
        len(ph), len(teams), season, week,
    )
    return ph


def build_team_features(plays: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Mirror of run_experiment._build_all_curated_team_features (23 per-team features)."""
    base = compute_season_to_date_features(plays)
    addl = compute_additional_team_features(plays)
    situ = compute_situational_features(games)

    tf = base.merge(
        addl[["team", "season", "week"] + ALL_ADDITIONAL_TEAM_FEATURES],
        on=["team", "season", "week"], how="left",
    )
    tf = tf.merge(
        situ[["team", "season", "week"] + SITUATIONAL_TEAM_FEATURES],
        on=["team", "season", "week"], how="left",
    )
    return tf


# ── Core ──────────────────────────────────────────────────────────────────────


def generate_predictions(
    client: bigquery.Client,
    season: int,
    week: int,
) -> tuple[pd.DataFrame, dict]:
    """Train on everything completed before the target week; predict that week."""
    plays = load_plays(client)
    games = load_games(client)

    slate = games[(games["season"] == season) & (games["week"] == week)].copy()
    if slate.empty:
        raise SystemExit(
            f"No games found in curated.games for season {season} week {week}. "
            "Check the fixtures loaded before running."
        )
    logger.info("Target slate: %d games — %s week %d", len(slate), season, week)

    already_played = slate["home_covered"].notna().sum()
    if already_played:
        logger.warning(
            "%d of %d games on this slate already have results. Predicting them "
            "anyway, but they are no longer forward predictions.",
            already_played, len(slate),
        )

    # Make the unplayed slate visible to the feature builders.
    plays_aug = pd.concat(
        [plays, build_placeholder_plays(slate, season, week)],
        ignore_index=True,
    )

    team_features = build_team_features(plays_aug, games)

    matrix_cols = list(dict.fromkeys(ALL_CURATED_TEAM_FEATURES + ["rest_days"]))
    game_features = build_game_feature_matrix(games, team_features, team_feature_cols=matrix_cols)
    game_features = add_rest_differential(game_features)

    model_feat_cols = (
        [f"home_{c}" for c in ALL_CURATED_TEAM_FEATURES]
        + [f"away_{c}" for c in ALL_CURATED_TEAM_FEATURES]
        + GAME_CONTEXT_FEATURES
        + ["rest_differential"]
    )
    missing = [c for c in model_feat_cols if c not in game_features.columns]
    if missing:
        raise SystemExit(f"Feature columns missing from the matrix: {missing}")

    # Train on every completed game strictly before the target week.
    before_target = (game_features["season"] < season) | (
        (game_features["season"] == season) & (game_features["week"] < week)
    )
    train_df = game_features[before_target].dropna(subset=["home_covered"]).copy()
    test_df = game_features[
        (game_features["season"] == season) & (game_features["week"] == week)
    ].copy()

    if train_df.empty:
        raise SystemExit("No completed games available to train on.")

    seasons_trained = sorted(train_df["season"].unique().tolist())
    logger.info(
        "Training on %d completed games (%d-%d); predicting %d games",
        len(train_df), seasons_trained[0], seasons_trained[-1], len(test_df),
    )

    # Guard against the silent failure mode: a slate whose features never joined.
    feat_null_rate = test_df[model_feat_cols].isna().mean().mean()
    logger.info("Mean feature null rate on the target slate: %.1f%%", feat_null_rate * 100)
    if feat_null_rate > 0.5:
        raise SystemExit(
            f"Target slate features are {feat_null_rate:.0%} null — the team-week join "
            "did not land. Refusing to emit predictions built on imputed noise."
        )

    model = OLXGBModelV2(random_seed=42)
    model.fit(train_df[model_feat_cols], train_df["home_covered"].astype(int))
    probs = model.predict_proba(test_df[model_feat_cols])

    preds = test_df[
        ["game_id", "season", "week", "home_team", "away_team", "home_spread_close"]
    ].copy()
    preds["predicted_home_cover_prob"] = probs
    preds["predicted_side"] = np.where(probs > 0.5, "home", "away")
    preds["actual_home_covered"] = test_df["home_covered"].values
    preds["correct"] = pd.Series([pd.NA] * len(preds), dtype="Int64")
    preds["ol_mismatch_flag"] = (
        test_df["ol_mismatch_flag"].values if "ol_mismatch_flag" in test_df.columns else 0
    )
    preds["fold"] = 0
    preds = preds.sort_values("game_id").reset_index(drop=True)

    meta = {
        "seasons_trained": seasons_trained,
        "n_train": int(len(train_df)),
        "n_predicted": int(len(preds)),
        "feature_null_rate": float(feat_null_rate),
        "features": model_feat_cols,
        "feature_importance": model.feature_importance().to_dict(orient="records")[:25],
    }
    return preds, meta


# ── BigQuery writes ───────────────────────────────────────────────────────────


def upsert_production_config(client: bigquery.Client, meta: dict) -> None:
    """
    Keep exactly one config row for the rolling production model.

    gate_passed is written FALSE, truthfully.  Nothing here has cleared a
    success threshold, and the serving layer is responsible for making that
    visible rather than for hiding it (DEC-C).
    """
    features_json = json.dumps(
        [{"dataset": "curated", "column": c, "semantic_name": c} for c in meta["features"]]
    )
    query = f"""
        MERGE `{CONFIGS_TABLE}` T
        USING (SELECT @eid AS experiment_id) S
        ON T.experiment_id = S.experiment_id
        WHEN MATCHED THEN UPDATE SET
            status = 'complete',
            gate_passed = FALSE,
            features = PARSE_JSON(@features)
        WHEN NOT MATCHED THEN INSERT
            (experiment_id, name, created_at, status, gate_passed, target, features)
        VALUES
            (@eid, @name, CURRENT_TIMESTAMP(), 'complete', FALSE, 'ats_cover', PARSE_JSON(@features))
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("eid", "STRING", PRODUCTION_EXPERIMENT_ID),
            bigquery.ScalarQueryParameter("name", "STRING", PRODUCTION_EXPERIMENT_NAME),
            bigquery.ScalarQueryParameter("features", "STRING", features_json),
        ]
    )
    client.query(query, job_config=job_config).result()
    logger.info("experiment_configs: upserted %s", PRODUCTION_EXPERIMENT_NAME)


def replace_week_predictions(
    client: bigquery.Client,
    preds: pd.DataFrame,
    run_id: str,
    season: int,
    week: int,
) -> None:
    """
    Delete-then-insert this experiment's rows for the target week.

    Re-running mid-week (lines move, injuries land) must not leave two
    generations of prediction for the same game, which would let the serving
    endpoint return whichever it happened to read first.
    """
    delete_q = f"""
        DELETE FROM `{PREDS_TABLE}`
        WHERE experiment_id = @eid AND season = @season AND week = @week
    """
    client.query(
        delete_q,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("eid", "STRING", PRODUCTION_EXPERIMENT_ID),
                bigquery.ScalarQueryParameter("season", "INT64", season),
                bigquery.ScalarQueryParameter("week", "INT64", week),
            ]
        ),
    ).result()

    out = preds[[
        "game_id", "season", "week", "home_team", "away_team", "home_spread_close",
        "predicted_home_cover_prob", "predicted_side", "actual_home_covered",
        "correct", "ol_mismatch_flag", "fold",
    ]].copy()
    out.insert(0, "experiment_id", PRODUCTION_EXPERIMENT_ID)
    out.insert(0, "run_id", run_id)
    out["actual_home_covered"] = out["actual_home_covered"].astype(pd.BooleanDtype())
    out["correct"] = out["correct"].astype(pd.Int64Dtype())
    out["ol_mismatch_flag"] = out["ol_mismatch_flag"].fillna(0).astype("int64")

    job = client.load_table_from_dataframe(
        out,
        PREDS_TABLE,
        job_config=bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            schema=PREDS_SCHEMA,
        ),
    )
    job.result()
    logger.info("backtest_predictions: wrote %d rows (run_id=%s)", len(out), run_id)


def write_run_row(
    client: bigquery.Client,
    run_id: str,
    meta: dict,
    season: int,
    week: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "run_id": run_id,
        "experiment_id": PRODUCTION_EXPERIMENT_ID,
        "run_at": now,
        "completed_at": now,
        "status": "complete",
        "gate_passed": False,
        "n_games": meta["n_predicted"],
        "features": json.dumps(meta["features"]),
        "notes": (
            f"Forward prediction for {season} week {week}. "
            f"Trained on {meta['n_train']} completed games "
            f"({meta['seasons_trained'][0]}-{meta['seasons_trained'][-1]}). "
            "Not gate-passed: no experiment has cleared its success threshold."
        ),
    }
    errors = client.insert_rows_json(RUNS_TABLE, [row])
    if errors:
        logger.warning("backtest_runs insert returned errors: %s", errors)
    else:
        logger.info("backtest_runs: wrote run %s", run_id)


def grade_completed(client: bigquery.Client, season: int, week: int) -> None:
    """Backfill actual_home_covered / correct once results exist."""
    query = f"""
        UPDATE `{PREDS_TABLE}` p
        SET
          actual_home_covered = g.home_covered,
          correct = CASE
              WHEN g.home_covered IS NULL THEN NULL
              WHEN (p.predicted_side = 'home') = g.home_covered THEN 1
              ELSE 0
          END
        FROM `{PROJECT}.curated.games` g
        WHERE p.game_id = g.game_id
          AND p.experiment_id = @eid
          AND p.season = @season
          AND p.week = @week
          AND g.home_covered IS NOT NULL
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("eid", "STRING", PRODUCTION_EXPERIMENT_ID),
                bigquery.ScalarQueryParameter("season", "INT64", season),
                bigquery.ScalarQueryParameter("week", "INT64", week),
            ]
        ),
    )
    job.result()
    logger.info("Graded %s rows for %d week %d", job.num_dml_affected_rows, season, week)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Predict an upcoming NFL slate.")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true", help="Compute and report; write nothing to BigQuery.")
    ap.add_argument("--grade", action="store_true", help="Only backfill results for an already-predicted week.")
    args = ap.parse_args()

    client = bigquery.Client(project=PROJECT)

    if args.grade:
        grade_completed(client, args.season, args.week)
        return 0

    preds, meta = generate_predictions(client, args.season, args.week)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = REPORTS_DIR / f"forward_{args.season}_wk{args.week:02d}_{stamp}.csv"
    preds.to_csv(csv_path, index=False)
    logger.info("Wrote %s", csv_path)

    print()
    print(f"  {args.season} WEEK {args.week} — {len(preds)} games")
    print(f"  Trained on {meta['n_train']:,} completed games "
          f"({meta['seasons_trained'][0]}-{meta['seasons_trained'][-1]})")
    print("  NOT VALIDATED — no experiment has cleared its success threshold.")
    print()
    print(f"  {'MATCHUP':<16}{'SPREAD':>8}{'PICK':>7}{'P(home cover)':>15}")
    print("  " + "-" * 46)
    for _, r in preds.iterrows():
        spread = r["home_spread_close"]
        spread_s = f"{spread:+.1f}" if pd.notna(spread) else "n/a"
        pick = r["home_team"] if r["predicted_side"] == "home" else r["away_team"]
        print(f"  {r['away_team']+' @ '+r['home_team']:<16}{spread_s:>8}{pick:>7}"
              f"{r['predicted_home_cover_prob']:>15.3f}")
    print()

    if args.dry_run:
        print("  --dry-run: nothing written to BigQuery.")
        return 0

    run_id = str(uuid.uuid4())
    upsert_production_config(client, meta)
    replace_week_predictions(client, preds, run_id, args.season, args.week)
    write_run_row(client, run_id, meta, args.season, args.week)
    print(f"  Written. experiment_id={PRODUCTION_EXPERIMENT_ID} run_id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

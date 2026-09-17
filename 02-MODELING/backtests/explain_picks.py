#!/usr/bin/env python3
"""
Explain picks made before per-game explanations existed (STAGE 1.6 of
PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md).

Retrains exactly as production did for that (season, week), re-predicts, and
compares the reproduced probabilities against what is already stored in
experiments.backtest_predictions. Only on an exact reproduction (every game
within REPRODUCTION_TOLERANCE) does it compute and store explanations for that
week's stored picks.

Reproduction guard — hard STOP if it fails
-------------------------------------------
If any game's reproduced probability differs from the stored one by more than
REPRODUCTION_TOLERANCE (1e-6), this script writes NOTHING and exits non-zero
with a diff table. A mismatch means the data (or feature set) under the model
has changed since the picks were actually made — the explanation would then
describe a model that never made those picks. See "Options on a guard
failure" below.

Linux only
----------
2026-09-17 (QUESTIONS.md): reproduction was confirmed byte-close (max diff
2.86e-08) inside the production Cloud Run image, and off by up to 0.097 with
side flips on a Windows dev machine running the IDENTICAL pinned package
versions (pandas 1.5.3 / numpy 1.26.4 / scikit-learn 1.9.0 / xgboost 3.2.0).
Cause: platform-compiled numpy/BLAS binaries differ between Windows and
Linux, not the version pins. The reproduction guard is therefore only
meaningful on Linux — run_reproduction_guard() refuses to run anywhere else,
with no CLI flag to bypass it (allow_non_linux is a function parameter for
tests only, not a documented flag). Every real run's environment
(platform, Python, pandas/numpy/scikit-learn/xgboost versions) is logged and
written next to the diff CSV, so a future reproduction can be checked against
the environment that actually produced a stored result.

Which feature config counts as "exactly as production did"
------------------------------------------------------------
predict_upcoming.py's live feature set changed over time (see ADR-013): the
prior-season blend went live 2026-09-16, AFTER 2026 week 1's picks were made
and played, so week 1 was produced on the un-blended base 23
(ALL_CURATED_TEAM_FEATURES). Week 2 onward (2026) was produced on the blended
PRODUCTION_FEATURE_LIST at PRODUCTION_BLEND_N. HISTORICAL_FEATURE_CONFIG below
is the explicit, dated record of that — extend it (not predict_upcoming.py's
current defaults) whenever the live feature set changes again, or this guard
will "correctly" fail against every week produced before the change.

Options on a guard failure
---------------------------
Matt chooses one:
  1. --approximate: store explanations from the nearest reproducible model
     anyway, every row marked is_approximate=True with reproduction_max_diff
     recorded — NOT a faithful reproduction of the live pick. clean_forward is
     untouched by this: it keeps its one meaning (not regenerated after
     kickoff) regardless of whether the reproduction was exact or approximate.
  2. Investigate the data change first (most likely a downstream nflverse /
     curated-table rebuild altering historical 2015-2025 aggregates since the
     picks were made — see SESSION-LOG-2026-09-15-to-17.md, "Picks changed
     between two runs on 2026-09-15"). Re-run this script once resolved.

Usage
-----
    python backtests/explain_picks.py --season 2026 --week 1
    python backtests/explain_picks.py --season 2026 --week 1 --dry-run
    python backtests/explain_picks.py --season 2026 --week 1 --approximate
"""
from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests.predict_upcoming import (  # noqa: E402
    ALL_CURATED_TEAM_FEATURES,
    PRODUCTION_BLEND_N,
    PRODUCTION_EXPERIMENT_ID,
    PRODUCTION_FEATURE_LIST,
    generate_predictions,
)
from backtests.environment import environment_fingerprint  # noqa: E402
from backtests.explanations import build_explanations, feature_list_hash  # noqa: E402
from backtests.explanations_bq import (  # noqa: E402
    ensure_explanations_table,
    write_explanations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
PREDS_TABLE = f"{PROJECT}.experiments.backtest_predictions"
REPORTS_DIR = ROOT / "backtests" / "reports"

REPRODUCTION_TOLERANCE = 1e-6

# ── Dated record of which feature config produced each historical week ──────
#
# (season, week) -> (feature_list, blend_n). Anything not listed falls back to
# the blend go-live cutover: 2026 week 1 (before the 2026-09-16 go-live) is
# un-blended; everything from 2026 week 2 onward is the current
# PRODUCTION_FEATURE_LIST / PRODUCTION_BLEND_N. Extend this dict explicitly
# the next time the live feature set changes — do not let this script infer
# "current defaults" for a week that predates the change that created them.
_BLEND_GO_LIVE_SEASON_WEEK = (2026, 2)  # first week produced on the blend

HISTORICAL_FEATURE_CONFIG: dict[tuple[int, int], tuple[list[str], int]] = {
    (2026, 1): (ALL_CURATED_TEAM_FEATURES, 4),  # blend_n unused when unblended; 4 is the harmless default
}

# Known picks regenerated after their game had kicked off (DEFECT-3,
# 2026-09-13 — see SESSION-LOG). Kept in the analysis but flagged.
KNOWN_NOT_CLEAN_FORWARD: dict[tuple[int, int], set[str]] = {
    (2026, 1): {"2026_01_SF_LA", "2026_01_NE_SEA"},
}


def resolve_historical_config(season: int, week: int) -> tuple[list[str], int]:
    if (season, week) in HISTORICAL_FEATURE_CONFIG:
        return HISTORICAL_FEATURE_CONFIG[(season, week)]
    if (season, week) < _BLEND_GO_LIVE_SEASON_WEEK:
        return ALL_CURATED_TEAM_FEATURES, 4
    return PRODUCTION_FEATURE_LIST, PRODUCTION_BLEND_N


def load_stored_predictions(client: bigquery.Client, season: int, week: int) -> pd.DataFrame:
    query = f"""
        SELECT game_id, home_team, away_team, predicted_home_cover_prob, predicted_side
        FROM `{PREDS_TABLE}`
        WHERE experiment_id = @eid AND season = @season AND week = @week
        ORDER BY game_id
    """
    rows = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("eid", "STRING", PRODUCTION_EXPERIMENT_ID),
                bigquery.ScalarQueryParameter("season", "INT64", season),
                bigquery.ScalarQueryParameter("week", "INT64", week),
            ]
        ),
    ).result()
    df = rows.to_dataframe()
    if df.empty:
        raise SystemExit(
            f"No stored predictions for experiment {PRODUCTION_EXPERIMENT_ID}, "
            f"season {season} week {week}. Nothing to explain."
        )
    return df


def compare_predictions(stored: pd.DataFrame, reproduced: pd.DataFrame) -> pd.DataFrame:
    m = stored.merge(
        reproduced[["game_id", "predicted_home_cover_prob", "predicted_side"]].rename(
            columns={
                "predicted_home_cover_prob": "reproduced_prob",
                "predicted_side": "reproduced_side",
            }
        ),
        on="game_id",
        how="outer",
        indicator=True,
    )
    m["diff"] = (m["predicted_home_cover_prob"] - m["reproduced_prob"]).abs()
    m["side_flipped"] = m["predicted_side"] != m["reproduced_side"]
    return m.sort_values("game_id").reset_index(drop=True)


def _check_linux(allow_non_linux: bool) -> None:
    """
    Refuse to run the reproduction guard anywhere but Linux.

    2026-09-17 finding (QUESTIONS.md): reproduction matched the stored picks
    to within 2.86e-08 inside the production Linux image, and was off by up
    to 0.097 with side flips on Windows running the SAME pinned package
    versions. A "guard failure" measured on Windows doesn't mean what this
    script's docstring says it means, so it must not run there at all.

    allow_non_linux exists ONLY for unit tests that exercise the comparison
    logic without needing a Linux host — there is no CLI flag for it.
    """
    if allow_non_linux:
        return
    system = platform.system()
    if system != "Linux":
        raise SystemExit(
            f"Refusing to run the reproduction guard on {system!r}. Reproduction was "
            "confirmed (2026-09-17, QUESTIONS.md) to only match the stored picks inside "
            "the Linux production image — the same pinned package versions on Windows "
            "produce different floating-point results and up to 0.097 probability "
            "drift with side flips, which is not a real guard failure. Run this inside "
            "the production image (a Cloud Run job execution or a one-off Cloud Build "
            "step using it), not on a local Windows/macOS machine."
        )


def run_reproduction_guard(
    client: bigquery.Client,
    season: int,
    week: int,
    tolerance: float = REPRODUCTION_TOLERANCE,
    allow_non_linux: bool = False,
    curated_dataset: str = "curated",
) -> tuple[bool, pd.DataFrame, pd.DataFrame, dict]:
    """
    Returns (passed, diff_table, reproduced_preds, meta).

    passed=False means: write nothing. diff_table always has one row per
    game_id present in either the stored set or the reproduced set (an
    "_merge" column of anything but "both" is itself a failure).

    Refuses to run anywhere but Linux (see _check_linux) unless
    allow_non_linux=True — that parameter exists only for unit tests.

    curated_dataset defaults to "curated". Pass a recovered snapshot dataset
    (e.g. "scratch_timetravel") to reproduce against data as it stood before
    a later rebuild changed the live curated tables.
    """
    _check_linux(allow_non_linux)
    stored = load_stored_predictions(client, season, week)
    feature_list, blend_n = resolve_historical_config(season, week)
    logger.info(
        "Reproducing %d week %d with %d features (blend_n=%s, %s) against %s",
        season, week, len(feature_list), blend_n,
        "unblended" if feature_list is ALL_CURATED_TEAM_FEATURES else "blended",
        curated_dataset,
    )
    reproduced, meta = generate_predictions(
        client, season, week, feature_list=feature_list, blend_n=blend_n,
        curated_dataset=curated_dataset,
    )

    diff_table = compare_predictions(stored, reproduced)
    mismatched = diff_table[
        (diff_table["_merge"] != "both")
        | (diff_table["diff"] > tolerance)
        | (diff_table["side_flipped"])
    ]
    passed = mismatched.empty
    return passed, diff_table, reproduced, meta


def _print_diff_table(diff_table: pd.DataFrame) -> None:
    print()
    print(f"  {'GAME':<16}{'STORED':>10}{'REPRODUCED':>12}{'DIFF':>10}{'SIDE FLIP':>11}")
    print("  " + "-" * 60)
    for _, r in diff_table.iterrows():
        stored_s = f"{r['predicted_home_cover_prob']:.4f}" if pd.notna(r["predicted_home_cover_prob"]) else "MISSING"
        repro_s = f"{r['reproduced_prob']:.4f}" if pd.notna(r["reproduced_prob"]) else "MISSING"
        diff_s = f"{r['diff']:.4f}" if pd.notna(r["diff"]) else "n/a"
        flip_s = "YES" if r["side_flipped"] else ""
        print(f"  {r['game_id']:<16}{stored_s:>10}{repro_s:>12}{diff_s:>10}{flip_s:>11}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Explain historical picks, with a hard reproduction guard.")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--tolerance", type=float, default=REPRODUCTION_TOLERANCE)
    ap.add_argument(
        "--curated-dataset", default="curated",
        help="BigQuery dataset to load games/plays from, laid out like curated "
             "(default: curated). Pass a recovered snapshot dataset (e.g. "
             "scratch_timetravel) to reproduce against data as it stood before "
             "a later rebuild changed the live curated tables.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Run the guard and report; write nothing regardless of outcome.")
    ap.add_argument(
        "--approximate", action="store_true",
        help="On a guard failure, store explanations from the reproduced (non-matching) "
             "model anyway, with every row marked is_approximate=True and "
             "reproduction_max_diff recorded. Does not touch clean_forward. "
             "Only pass this after Matt has chosen this option on a reported STOP.",
    )
    args = ap.parse_args()

    env = environment_fingerprint()
    logger.info("Environment: %s", json.dumps(env))

    client = bigquery.Client(project=PROJECT)

    # No CLI flag for allow_non_linux — _check_linux inside run_reproduction_guard
    # refuses non-Linux unconditionally for a real invocation of this script.
    passed, diff_table, reproduced, meta = run_reproduction_guard(
        client, args.season, args.week, tolerance=args.tolerance,
        curated_dataset=args.curated_dataset,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    diff_path = REPORTS_DIR / f"explain_picks_{args.season}_wk{args.week:02d}_{stamp}_diff.csv"
    diff_table.to_csv(diff_path, index=False)
    env_path = REPORTS_DIR / f"explain_picks_{args.season}_wk{args.week:02d}_{stamp}_env.json"
    env_path.write_text(json.dumps(env, indent=2), encoding="utf-8")
    logger.info("Environment fingerprint written: %s", env_path)

    if not passed and not args.approximate:
        print()
        print("  " + "=" * 60)
        print(f"  STOP — reproduction guard failed for {args.season} week {args.week}")
        print("  " + "=" * 60)
        _print_diff_table(diff_table)
        print(f"  Full diff table: {diff_path}")
        print()
        print("  Nothing was written. Options:")
        print("    1. --approximate : store explanations from this (non-matching) model,")
        print("       every row in this run marked is_approximate=True with the observed")
        print("       reproduction_max_diff recorded — clearly not the model that made")
        print("       these picks, without touching clean_forward's own meaning.")
        print("    2. Investigate the data change first (most likely a downstream")
        print("       nflverse/curated-table rebuild since the picks were made — see")
        print("       SESSION-LOG-2026-09-15-to-17.md, 'Picks changed between two runs').")
        print("       Re-run this script once resolved.")
        print()
        return 1

    if args.dry_run:
        print(f"  --dry-run: guard {'PASSED' if passed else 'FAILED (would need --approximate)'}. Nothing written.")
        _print_diff_table(diff_table)
        return 0 if passed else 1

    # clean_forward means ONLY "not regenerated after kickoff" — it is never
    # repurposed to flag an approximate reproduction. That's is_approximate's job.
    not_clean = KNOWN_NOT_CLEAN_FORWARD.get((args.season, args.week), set())
    clean_forward_map = {
        gid: (gid not in not_clean) for gid in reproduced["game_id"]
    }

    reproduction_max_diff = float(diff_table["diff"].max())
    is_approximate = not passed  # only reachable here if passed, or --approximate overrode a failure

    exp = build_explanations(
        meta["_model"],
        meta["_test_X_raw"],
        meta["_games_meta"],
        meta["_predicted_side"],
        meta["_predicted_home_cover_prob"],
        team_features=meta.get("_team_features"),
    )

    ensure_explanations_table(client)
    run_id = str(uuid.uuid4())
    n = write_explanations(
        client,
        exp,
        run_id=run_id,
        experiment_id=PRODUCTION_EXPERIMENT_ID,
        model_name="ol_xgb_v2",
        feature_list_hash=feature_list_hash(meta["features"]),
        blend_n=meta.get("blend_n"),
        clean_forward=clean_forward_map,
        reproduction_max_diff=reproduction_max_diff,
        is_approximate=is_approximate,
    )

    status = "APPROXIMATE (guard failed, --approximate used)" if is_approximate else "exact reproduction"
    print()
    print(f"  Wrote {n} explanation rows for {args.season} week {args.week} ({status}).")
    print(f"  run_id={run_id}  reproduction_max_diff={reproduction_max_diff:.6g}  "
          f"not_clean_forward={sorted(not_clean) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

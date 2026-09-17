"""
Unit tests for backtests/walk_forward.py's explanation storage
(PROMPT-STAGE1-FINISH-EXPLANATIONS.md §4). Synthetic data only, no BigQuery.

Run:
    cd 02-MODELING && python -m pytest backtests/test_walk_forward.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests.walk_forward import run_walk_forward  # noqa: E402

FEATURES = ["home_ol_sack_rate", "away_ol_sack_rate", "home_def_sack_rate", "away_def_sack_rate"]
FOLDS = [([2019], 2020), ([2019, 2020], 2021)]


def _synthetic_game_features(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    game_n = 0
    for season in (2019, 2020, 2021):
        for week in (1, 2):
            for g in range(6):
                row = {
                    "game_id": f"{season}_{week:02d}_G{g}",
                    "season": season,
                    "week": week,
                    "home_team": f"H{g}",
                    "away_team": f"A{g}",
                    "home_spread_close": -3.0,
                }
                for f in FEATURES:
                    row[f] = rng.normal()
                row["home_covered"] = int(row["home_ol_sack_rate"] < row["away_ol_sack_rate"])
                rows.append(row)
                game_n += 1
    return pd.DataFrame(rows)


def _team_features(game_features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in game_features.iterrows():
        rows.append({
            "team": r["home_team"], "season": r["season"], "week": r["week"],
            "ol_sack_rate": r["home_ol_sack_rate"], "def_sack_rate": r["home_def_sack_rate"],
        })
        rows.append({
            "team": r["away_team"], "season": r["season"], "week": r["week"],
            "ol_sack_rate": r["away_ol_sack_rate"], "def_sack_rate": r["away_def_sack_rate"],
        })
    return pd.DataFrame(rows)


def test_store_explanations_default_on_produces_one_row_per_game_times_feature():
    gf = _synthetic_game_features()
    result = run_walk_forward(
        gf, experiment_id="exp-1", model_features=FEATURES, folds_override=FOLDS,
    )
    all_exp = result.all_explanations()
    n_test_games = sum(fr.n_games + fr.pushes for fr in result.folds)
    assert len(all_exp) == n_test_games * len(FEATURES)
    assert set(all_exp["feature"]) == set(FEATURES)
    assert set(all_exp["fold"]) == {1, 2}


def test_store_explanations_false_leaves_it_empty():
    gf = _synthetic_game_features()
    result = run_walk_forward(
        gf, experiment_id="exp-1", model_features=FEATURES, folds_override=FOLDS,
        store_explanations=False,
    )
    for fr in result.folds:
        assert fr.explanations is None
    assert result.all_explanations().empty


def test_league_pctile_populated_when_team_features_passed():
    gf = _synthetic_game_features()
    tf = _team_features(gf)
    result = run_walk_forward(
        gf, experiment_id="exp-1", model_features=FEATURES, folds_override=FOLDS,
        team_features=tf,
    )
    all_exp = result.all_explanations()
    team_rows = all_exp[all_exp["side"].isin(["home", "away"])]
    assert team_rows["league_pctile"].notna().all()


def test_contributions_plus_bias_reconstruct_log_odds():
    """Same guarantee explain_picks.py relies on: contributions sum to the
    model's own log-odds within a tight tolerance."""
    gf = _synthetic_game_features()
    result = run_walk_forward(
        gf, experiment_id="exp-1", model_features=FEATURES, folds_override=FOLDS,
    )
    all_exp = result.all_explanations()
    per_row = all_exp.groupby("row_id").agg(
        total=("contribution_logodds", "sum"), bias=("bias_logodds", "first"),
        row_sum=("row_sum_logodds", "first"),
    )
    assert np.allclose(per_row["total"] + per_row["bias"], per_row["row_sum"], atol=1e-4)


def test_explanations_failure_does_not_break_the_backtest(monkeypatch):
    """A family-map gap (or any explanation-building failure) must not take
    down the backtest's own metrics — only that fold's explanations skip."""
    import backtests.walk_forward as wf

    def _boom(*a, **kw):
        raise KeyError("no family mapped for some feature")

    monkeypatch.setattr(wf, "build_explanations", _boom)
    gf = _synthetic_game_features()
    result = run_walk_forward(
        gf, experiment_id="exp-1", model_features=FEATURES, folds_override=FOLDS,
    )
    assert result.total_n_games > 0
    for fr in result.folds:
        assert fr.explanations is None
    assert result.all_explanations().empty

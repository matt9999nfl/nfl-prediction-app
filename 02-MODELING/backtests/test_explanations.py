"""
Unit tests for backtests/explanations.py (STAGE 1.2). Synthetic data only.

Run:
    cd 02-MODELING && python -m pytest backtests/test_explanations.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models.ol_xgb import OLXGBModel  # noqa: E402
from backtests.explanations import (  # noqa: E402
    build_explanations,
    matchup_view,
    top_drivers,
    feature_list_hash,
)

FEATURES = [
    "home_ol_sack_rate", "away_ol_sack_rate",
    "home_def_sack_rate", "away_def_sack_rate",
    "temp", "wind",
]


def _toy_model_and_games(n_games=6, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n_games, len(FEATURES))), columns=FEATURES)
    logit = 1.2 * X["home_ol_sack_rate"] - 0.9 * X["away_ol_sack_rate"]
    y = (logit > 0).astype(int)

    model = OLXGBModel(random_seed=42)
    model.fit(X, y)
    probs = model.predict_proba(X)

    games_meta = pd.DataFrame({
        "game_id": [f"2026_01_G{i}" for i in range(n_games)],
        "season": 2026,
        "week": 1,
        "home_team": [f"H{i}" for i in range(n_games)],
        "away_team": [f"A{i}" for i in range(n_games)],
    })
    predicted_side = pd.Series(np.where(probs > 0.5, "home", "away"), index=X.index)
    predicted_prob = pd.Series(probs, index=X.index)
    return model, X, games_meta, predicted_side, predicted_prob


def test_build_explanations_basic_shape():
    model, X, games_meta, side, prob = _toy_model_and_games()
    exp = build_explanations(model, X, games_meta, side, prob)

    assert set(exp["game_id"]) == set(games_meta["game_id"])
    assert set(exp["feature"]) == set(FEATURES)
    for col in ("side", "family", "raw_value", "was_imputed",
                "contribution_logodds", "pick_direction_contribution",
                "abs_rank", "bias_logodds", "predicted_side",
                "predicted_home_cover_prob", "league_pctile"):
        assert col in exp.columns


def test_pick_direction_contribution_sign():
    model, X, games_meta, side, prob = _toy_model_and_games()
    exp = build_explanations(model, X, games_meta, side, prob)

    home_rows = exp[exp["predicted_side"] == "home"]
    away_rows = exp[exp["predicted_side"] == "away"]
    assert np.allclose(
        home_rows["pick_direction_contribution"], home_rows["contribution_logodds"]
    )
    assert np.allclose(
        away_rows["pick_direction_contribution"], -away_rows["contribution_logodds"]
    )


def test_side_and_family_resolved_for_every_row():
    model, X, games_meta, side, prob = _toy_model_and_games()
    exp = build_explanations(model, X, games_meta, side, prob)
    assert exp["side"].isin(["home", "away", "game"]).all()
    assert exp["family"].notna().all()
    assert set(exp.loc[exp["feature"] == "temp", "side"]) == {"game"}
    assert set(exp.loc[exp["feature"] == "home_ol_sack_rate", "side"]) == {"home"}


def test_league_pctile_ranks_teams_within_the_same_week():
    model, X, games_meta, side, prob = _toy_model_and_games()

    # Build a team_features table where each "home" team's ol_sack_rate value
    # matches X so percentile is computable, plus a couple of extra teams to
    # rank against.
    team_rows = []
    for i, row in X.iterrows():
        team_rows.append({"team": games_meta.loc[i, "home_team"], "season": 2026, "week": 1,
                           "ol_sack_rate": row["home_ol_sack_rate"], "def_sack_rate": row["home_def_sack_rate"]})
        team_rows.append({"team": games_meta.loc[i, "away_team"], "season": 2026, "week": 1,
                           "ol_sack_rate": row["away_ol_sack_rate"], "def_sack_rate": row["away_def_sack_rate"]})
    team_features = pd.DataFrame(team_rows)

    exp = build_explanations(model, X, games_meta, side, prob, team_features=team_features)
    team_side_rows = exp[exp["feature"].isin(["home_ol_sack_rate", "away_ol_sack_rate"])]
    assert team_side_rows["league_pctile"].notna().all()
    assert (team_side_rows["league_pctile"] >= 0).all() and (team_side_rows["league_pctile"] <= 100).all()

    # game-level features get no percentile
    assert exp.loc[exp["feature"] == "temp", "league_pctile"].isna().all()


def test_matchup_view_nets_home_and_away_by_family():
    model, X, games_meta, side, prob = _toy_model_and_games()
    exp = build_explanations(model, X, games_meta, side, prob)
    mv = matchup_view(exp)

    assert set(mv.columns) >= {"game_id", "family", "home_contribution", "away_contribution", "net"}
    # net must equal home + away for every row
    assert np.allclose(mv["net"], mv["home_contribution"] + mv["away_contribution"])
    # game-level features (side='game') never appear in the matchup view
    assert "temp" not in set(mv["family"])  # family name isn't a feature name, sanity check only
    # every family present is one of the mapped families for a home/away feature
    from features.families import feature_family
    expected_families = {feature_family(f) for f in FEATURES if not f in ("temp", "wind")}
    assert set(mv["family"]) <= expected_families


def test_top_drivers_orders_by_abs_pick_direction_contribution():
    model, X, games_meta, side, prob = _toy_model_and_games()
    exp = build_explanations(model, X, games_meta, side, prob)
    gid = games_meta["game_id"].iloc[0]
    top = top_drivers(exp, gid, n=3)
    assert len(top) == 3
    vals = top["pick_direction_contribution"].abs().tolist()
    assert vals == sorted(vals, reverse=True)


def test_feature_list_hash_is_stable_and_order_sensitive():
    h1 = feature_list_hash(["a", "b", "c"])
    h2 = feature_list_hash(["a", "b", "c"])
    h3 = feature_list_hash(["c", "b", "a"])
    assert h1 == h2
    assert h1 != h3

"""
Unit tests for backtests/analyze_week_explanations.py (PROMPT-WEEK1-ANALYSIS.md).
Synthetic data only — no BigQuery network calls.

Run:
    cd 02-MODELING && python -m pytest backtests/test_analyze_week_explanations.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests import analyze_week_explanations as awe  # noqa: E402


def _exp_row(game_id, feature, side, family, predicted_side, contribution, **kw):
    row = {
        "game_id": game_id,
        "season": 2026,
        "week": 1,
        "feature": feature,
        "side": side,
        "family": family,
        "raw_value": kw.get("raw_value", 1.0),
        "league_pctile": kw.get("league_pctile", 50.0),
        "was_imputed": kw.get("was_imputed", False),
        "contribution_logodds": contribution,
        "pick_direction_contribution": contribution if predicted_side == "home" else -contribution,
        "abs_rank": kw.get("abs_rank", 1),
        "bias_logodds": kw.get("bias_logodds", 0.0),
        "predicted_side": predicted_side,
        "predicted_home_cover_prob": kw.get("predicted_home_cover_prob", 0.6),
        "clean_forward": kw.get("clean_forward", True),
        "is_approximate": kw.get("is_approximate", False),
        "reproduction_max_diff": kw.get("reproduction_max_diff", 0.0),
    }
    return row


def _live_row(game_id, live_side, **kw):
    return {
        "game_id": game_id,
        "home_team": kw.get("home_team", "H"),
        "away_team": kw.get("away_team", "A"),
        "home_spread_close": kw.get("home_spread_close", -2.0),
        "live_predicted_home_cover_prob": kw.get("live_predicted_home_cover_prob", 0.6),
        "live_predicted_side": live_side,
        "actual_home_covered": kw.get("actual_home_covered", pd.NA),
        "correct": kw.get("correct", pd.NA),
    }


# ── pick-direction sign / re-signing toward the live pick ───────────────────


def test_resign_toward_live_pick_no_mismatch_keeps_sign():
    exp_df = pd.DataFrame([
        _exp_row("G1", "home_ol_sack_rate", "home", "OL pass protection", "home", 0.5),
        _exp_row("G1", "away_ol_sack_rate", "away", "OL pass protection", "home", -0.3),
    ])
    live_df = pd.DataFrame([_live_row("G1", "home")])

    merged = awe.resign_toward_live_pick(exp_df, live_df)
    assert not merged["side_mismatch"].any()
    assert np.allclose(merged["pick_direction_live"], merged["pick_direction_contribution"])


def test_resign_toward_live_pick_flips_on_mismatch():
    exp_df = pd.DataFrame([
        _exp_row("G1", "home_ol_sack_rate", "home", "OL pass protection", "away", 0.5),
        _exp_row("G1", "away_ol_sack_rate", "away", "OL pass protection", "away", -0.3),
    ])
    live_df = pd.DataFrame([_live_row("G1", "home")])

    merged = awe.resign_toward_live_pick(exp_df, live_df)
    assert merged["side_mismatch"].all()
    assert np.allclose(merged["pick_direction_live"], -merged["pick_direction_contribution"])


def test_resign_toward_live_pick_raises_on_unmatched_game():
    exp_df = pd.DataFrame([_exp_row("G1", "home_ol_sack_rate", "home", "OL pass protection", "home", 0.5)])
    live_df = pd.DataFrame([_live_row("G2", "home")])
    with pytest.raises(ValueError):
        awe.resign_toward_live_pick(exp_df, live_df)


# ── side-mismatch exclusion in aggregate "toward the pick" statistics ───────


def test_family_push_stats_excludes_mismatched_games_in_13_game_column():
    # G1: no mismatch, family net positive (pushes toward pick).
    # G2: mismatch, family net positive toward the LIVE pick after resigning,
    #     but must be excluded from the "13 games" column.
    exp_df = pd.DataFrame([
        _exp_row("G1", "home_ol_sack_rate", "home", "OL pass protection", "home", 0.5),
        _exp_row("G2", "home_ol_sack_rate", "home", "OL pass protection", "away", 0.5),
    ])
    live_df = pd.DataFrame([_live_row("G1", "home"), _live_row("G2", "home")])
    resigned = awe.resign_toward_live_pick(exp_df, live_df)
    mismatched = set(resigned.loc[resigned["side_mismatch"], "game_id"])
    assert mismatched == {"G2"}

    stats = awe.family_push_stats(resigned, mismatched)
    row = stats[stats["family"] == "OL pass protection"].iloc[0]
    assert row["n_games_16"] == 2
    assert row["n_games_13"] == 1
    # Both games push toward the (live) pick after resigning, but only G1
    # counts once mismatches are excluded.
    assert row["pushed_toward_pick_frac_16"] == 1.0
    assert row["pushed_toward_pick_frac_13"] == 1.0


def test_top_drivers_orders_by_abs_pick_direction_live():
    exp_df = pd.DataFrame([
        _exp_row("G1", "f1", "home", "QB", "home", 0.1, abs_rank=3),
        _exp_row("G1", "f2", "home", "QB", "home", 0.9, abs_rank=1),
        _exp_row("G1", "f3", "away", "QB", "home", -0.5, abs_rank=2),
    ])
    live_df = pd.DataFrame([_live_row("G1", "home")])
    resigned = awe.resign_toward_live_pick(exp_df, live_df)
    top = awe.top_drivers(resigned, "G1", n=3)
    assert top["feature"].tolist() == ["f2", "f3", "f1"]


# ── reconstruction check ─────────────────────────────────────────────────────


def test_check_reconstruction_passes_when_contributions_sum_to_logit():
    p = 0.7
    logit_p = np.log(p / (1 - p))
    bias = 0.1
    c1, c2 = 0.3, logit_p - bias - 0.3
    exp_df = pd.DataFrame([
        _exp_row("G1", "f1", "home", "QB", "home", c1, bias_logodds=bias, predicted_home_cover_prob=p),
        _exp_row("G1", "f2", "home", "QB", "home", c2, bias_logodds=bias, predicted_home_cover_prob=p),
    ])
    recon = awe.check_reconstruction(exp_df)
    assert recon.iloc[0]["passed"]
    assert recon.iloc[0]["diff"] < 1e-9


def test_check_reconstruction_fails_on_a_real_mismatch():
    p = 0.7
    exp_df = pd.DataFrame([
        _exp_row("G1", "f1", "home", "QB", "home", 0.3, bias_logodds=0.1, predicted_home_cover_prob=p),
        _exp_row("G1", "f2", "home", "QB", "home", 0.05, bias_logodds=0.1, predicted_home_cover_prob=p),
    ])
    recon = awe.check_reconstruction(exp_df)
    assert not recon.iloc[0]["passed"]


# ── favourite/underdog and key-number helpers ────────────────────────────────


@pytest.mark.parametrize("spread,expected", [(-3.0, "home"), (3.0, "away"), (0.0, "pickem"), (None, "unknown")])
def test_favorite_or_underdog(spread, expected):
    assert awe.favorite_or_underdog(spread) == expected


@pytest.mark.parametrize("spread,expected", [(3.0, 3), (-3.2, 3), (7.4, 7), (10.0, None), (0.0, None)])
def test_near_key_number(spread, expected):
    assert awe.near_key_number(spread) == expected


# ── moneyline de-vig ──────────────────────────────────────────────────────────


def test_devig_moneylines_sums_to_one():
    ml_df = pd.DataFrame([{"game_id": "G1", "home_moneyline": -150.0, "away_moneyline": 130.0}])
    out = awe.devig_moneylines(ml_df)
    row = out.iloc[0]
    assert row["home_devigged_prob"] + (row["away_implied"] / (row["home_implied"] + row["away_implied"])) == pytest.approx(1.0)
    assert 0.0 < row["home_devigged_prob"] < 1.0


# ── clustering guards against degenerate input ───────────────────────────────


def test_cluster_games_raises_on_all_zero_vector():
    matrix = pd.DataFrame(
        {"QB": [0.0, 0.5], "form": [0.0, -0.2]}, index=["G1", "G2"],
    )
    with pytest.raises(ValueError):
        awe.cluster_games(matrix)

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
        "pick_time_spread": kw.get("pick_time_spread", -2.0),
        "live_predicted_home_cover_prob": kw.get("live_predicted_home_cover_prob", 0.6),
        "live_predicted_side": live_side,
        "actual_home_covered": kw.get("actual_home_covered", pd.NA),
        "correct": kw.get("correct", pd.NA),
    }


def _results_row(game_id, home_score, away_score, closing_spread):
    return {
        "game_id": game_id, "home_score": home_score, "away_score": away_score,
        "closing_spread": closing_spread,
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
#
# curated.games' home_spread_close follows the nflverse spread_line
# convention: POSITIVE means the HOME team is favoured (the opposite of
# betting notation). Getting this backwards is a recurring failure here
# (INC-001, 2026-09-10, 2026-09-14, 2026-09-18) —
# PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md requires tests that fail if it
# flips back.


@pytest.mark.parametrize("spread,expected", [(-3.0, "away"), (3.0, "home"), (0.0, "pickem"), (None, "unknown")])
def test_favorite_or_underdog(spread, expected):
    assert awe.favorite_or_underdog(spread) == expected


def test_positive_spread_9_5_makes_the_home_team_the_favourite():
    """
    2026_01_ARI_LAC: home_spread_close=+9.5, home_team=LAC. The report
    previously (wrongly) called ARI the favourite. LAC is the favourite —
    confirmed independently by a de-vigged home moneyline of 0.787
    (HANDOFF-2026-09-18-week1-analysis.md / PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md).
    """
    assert awe.favorite_or_underdog(9.5) == "home"


def test_a_pick_on_the_home_side_is_a_pick_on_the_favourite_when_spread_is_positive():
    games = pd.DataFrame([{
        "game_id": "2026_01_ARI_LAC", "closing_spread": 9.5, "live_predicted_side": "home",
    }])
    games["favorite"] = games["closing_spread"].apply(awe.favorite_or_underdog)
    games["picked_is_favorite"] = games["favorite"] == games["live_predicted_side"]
    assert games.iloc[0]["favorite"] == "home"
    assert bool(games.iloc[0]["picked_is_favorite"]) is True


@pytest.mark.parametrize("spread,expected", [(3.0, 3), (-3.2, 3), (7.4, 7), (10.0, None), (0.0, None)])
def test_near_key_number(spread, expected):
    assert awe.near_key_number(spread) == expected


# ── ATS label re-derivation against a fixture set of real 2026 week-1 rows ──
# margin > spread (this convention's ATS formula, matching
# verify_label_convention.py's C2 and predict_upcoming.grade_completed) must
# reproduce the label actually stored in curated.games. None of this script's
# code derives home_covered — this is a static regression fixture proving the
# convention this script's favourite/underdog logic relies on, independent of
# any production code path.
_ATS_FIXTURES = [
    # game_id, home_score, away_score, home_spread_close, stored home_covered
    ("2026_01_ARI_LAC", 14, 26, 9.5, False),
    ("2026_01_ATL_PIT", 20, 13, 6.5, True),
    ("2026_01_BAL_IND", 23, 41, -3.0, False),
    ("2026_01_DEN_KC", 31, 10, 2.5, True),
    ("2026_01_NE_SEA", 13, 10, 3.0, None),  # push: margin == spread
]


@pytest.mark.parametrize("game_id,home_score,away_score,spread,stored", _ATS_FIXTURES)
def test_ats_label_fixture_set(game_id, home_score, away_score, spread, stored):
    margin = home_score - away_score
    expected = None if margin == spread else (margin > spread)
    assert expected == stored, f"{game_id}: margin={margin:+g} spread={spread:+g}"


# ── favourite agreement guard (spread vs. de-vigged moneyline) ──────────────


def test_favorite_agreement_all_agree():
    games = pd.DataFrame([
        {"game_id": "G1", "favorite": "home"},
        {"game_id": "G2", "favorite": "away"},
    ])
    ml_table = pd.DataFrame([
        {"game_id": "G1", "home_devigged_prob": 0.7},
        {"game_id": "G2", "home_devigged_prob": 0.3},
    ])
    frac, mismatches = awe.favorite_agreement(games, ml_table)
    assert frac == 1.0
    assert mismatches.empty


def test_favorite_agreement_detects_mismatch():
    games = pd.DataFrame([
        {"game_id": "G1", "favorite": "home"},
        {"game_id": "G2", "favorite": "home"},
    ])
    ml_table = pd.DataFrame([
        {"game_id": "G1", "home_devigged_prob": 0.7},
        {"game_id": "G2", "home_devigged_prob": 0.3},  # moneyline says away favoured
    ])
    frac, mismatches = awe.favorite_agreement(games, ml_table)
    assert frac == 0.5
    assert mismatches["game_id"].tolist() == ["G2"]


def test_enforce_favorite_agreement_raises_below_floor():
    games = pd.DataFrame([
        {"game_id": f"G{i}", "favorite": "home"} for i in range(5)
    ])
    # Moneyline disagrees on 4 of 5 -> 20% agreement, well under the 80% floor.
    ml_table = pd.DataFrame([
        {"game_id": "G0", "home_devigged_prob": 0.7},
        {"game_id": "G1", "home_devigged_prob": 0.2},
        {"game_id": "G2", "home_devigged_prob": 0.2},
        {"game_id": "G3", "home_devigged_prob": 0.2},
        {"game_id": "G4", "home_devigged_prob": 0.2},
    ])
    with pytest.raises(SystemExit):
        awe.enforce_favorite_agreement(games, ml_table, season=2026, week=1)


def test_enforce_favorite_agreement_passes_above_floor():
    games = pd.DataFrame([{"game_id": f"G{i}", "favorite": "home"} for i in range(5)])
    ml_table = pd.DataFrame([{"game_id": f"G{i}", "home_devigged_prob": 0.7} for i in range(5)])
    frac, mismatches = awe.enforce_favorite_agreement(games, ml_table, season=2026, week=1)
    assert frac == 1.0
    assert mismatches.empty


# ── build_games_frame uses the CLOSING line (not pick-time) for favourite ───


def test_build_games_frame_favorite_uses_closing_not_pick_time_spread():
    """
    ARI@LAC-shaped fixture: the line moved between pick time (+9.5, still
    reading "home favoured" under this convention) and close (+8.5). Both
    read the same favourite here, so this also exercises the case that would
    catch a mix-up: pick_time_spread and closing_spread must be read from
    different source columns, not silently collapsed into one.
    """
    exp_df = pd.DataFrame([_exp_row("2026_01_ARI_LAC", "home_ol_sack_rate", "home", "OL pass protection", "home", 0.5)])
    live_df = pd.DataFrame([_live_row(
        "2026_01_ARI_LAC", "home", home_team="LAC", away_team="ARI", pick_time_spread=9.5,
    )])
    results_df = pd.DataFrame([_results_row("2026_01_ARI_LAC", 14, 26, 8.5)])
    resigned = awe.resign_toward_live_pick(exp_df, live_df)
    games = awe.build_games_frame(live_df, resigned, results_df, known_mismatches=None)

    row = games.iloc[0]
    assert row["pick_time_spread"] == 9.5
    assert row["closing_spread"] == 8.5
    assert row["favorite"] == "home"  # LAC, matching the closing line's sign
    assert bool(row["picked_is_favorite"]) is True


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

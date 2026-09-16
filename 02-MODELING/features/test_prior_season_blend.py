"""
Unit tests for the prior-season blend / prior-season-only features
(PROMPT-PRIOR-SEASON-BLEND.md §3a/§3b/§3c). Small synthetic frames only — no
BigQuery, no network.

Run:
    cd 02-MODELING && python -m pytest features/test_prior_season_blend.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features import ol_metrics as om  # noqa: E402
from features import comprehensive as comp  # noqa: E402
from features import situational as situ  # noqa: E402


# ── Synthetic play-by-play ───────────────────────────────────────────────────
#
# Two teams, AAA and BBB, across two seasons:
#   2020 — earliest season in the dataset, so it has NO prior season.
#     week 1: AAA  10 pass att, 1 sack,  2 explosive (yards>=20), epa 0.1
#             BBB  10 pass att, 2 sacks, 0 explosive,             epa -0.1
#     week 2: AAA  10 pass att, 3 sacks, 2 explosive,             epa 0.3
#             BBB  10 pass att, 1 sack,  0 explosive,             epa -0.1
#   AAA 2020 totals: pass_att=20, sacks=4 -> sack_rate=0.20; explosive=4 -> rate=0.20
#   BBB 2020 totals: pass_att=20, sacks=3 -> sack_rate=0.15; explosive=0 -> rate=0.00
#   League average (2020, the earliest season): sack_rate=0.175
#
#   2021 — has a prior season (2020).
#     week 1: AAA  10 pass att, 4 sacks, epa 0.5   BBB 10 pass att, 2 sacks, epa -0.2
#     week 2: AAA   5 pass att, 5 sacks, epa 0.9   BBB  5 pass att, 1 sack,  epa -0.3
#
# AAA week-2 2021 cum-through-week-1 = 10 att / 4 sacks -> base ol_sack_rate = 0.40
# AAA week-2 2021 blend (N=4): prior/game = 4/2=2 sacks, 20/2=10 att
#   blended = (4 + 4*2) / (10 + 4*10) = 12/50 = 0.24


def _pass_rows(game_id, season, week, off, deft, n_att, n_sack=0, n_explosive=0, epa=0.0):
    rows = []
    for i in range(n_att):
        rows.append(dict(
            game_id=game_id, season=season, week=week,
            posteam=off, defteam=deft, play_type="pass", down=1,
            sack=1 if i < n_sack else 0,
            qb_hit=0,
            epa=epa,
            yards_gained=25 if i < n_explosive else 5,
            cpoe=np.nan,
        ))
    return rows


def _base_plays(extra_2021_week2_aaa_sacks: int = 5) -> pd.DataFrame:
    rows = []
    rows += _pass_rows("2020_01", 2020, 1, "AAA", "BBB", 10, n_sack=1, n_explosive=2, epa=0.1)
    rows += _pass_rows("2020_01", 2020, 1, "BBB", "AAA", 10, n_sack=2, n_explosive=0, epa=-0.1)
    rows += _pass_rows("2020_02", 2020, 2, "AAA", "BBB", 10, n_sack=3, n_explosive=2, epa=0.3)
    rows += _pass_rows("2020_02", 2020, 2, "BBB", "AAA", 10, n_sack=1, n_explosive=0, epa=-0.1)
    rows += _pass_rows("2021_01", 2021, 1, "AAA", "BBB", 10, n_sack=4, n_explosive=0, epa=0.5)
    rows += _pass_rows("2021_01", 2021, 1, "BBB", "AAA", 10, n_sack=2, n_explosive=0, epa=-0.2)
    rows += _pass_rows("2021_02", 2021, 2, "AAA", "BBB", 5, n_sack=extra_2021_week2_aaa_sacks, n_explosive=0, epa=0.9)
    rows += _pass_rows("2021_02", 2021, 2, "BBB", "AAA", 5, n_sack=1, n_explosive=0, epa=-0.3)
    return pd.DataFrame(rows)


def _with_future_week3(plays: pd.DataFrame) -> pd.DataFrame:
    """Add an extreme week 3 (2021) for AAA — used for the no-look-ahead check."""
    extra = pd.DataFrame(
        _pass_rows("2021_03", 2021, 3, "AAA", "BBB", 10, n_sack=10, n_explosive=10, epa=5.0)
        + _pass_rows("2021_03", 2021, 3, "BBB", "AAA", 10, n_sack=0, n_explosive=0, epa=-5.0)
    )
    return pd.concat([plays, extra], ignore_index=True)


def _row(df: pd.DataFrame, team: str, season: int, week: int) -> pd.Series:
    match = df[(df["team"] == team) & (df["season"] == season) & (df["week"] == week)]
    assert len(match) == 1, f"expected exactly 1 row for {team} {season} wk{week}, got {len(match)}"
    return match.iloc[0]


# ── ol_metrics: the 12 count-based rate features ─────────────────────────────


class TestOlMetricsBlend:
    def test_week1_blend_equals_cold_start(self):
        """Week 1 has an empty current window, so blend == the prior season's
        full-season rate == today's cold-start value."""
        df = om.compute_season_to_date_features(_base_plays(), blend_n=4)
        r = _row(df, "AAA", 2021, 1)
        assert r["ol_sack_rate_blend"] == pytest.approx(0.2, abs=1e-6)
        assert r["ol_sack_rate"] == pytest.approx(r["ol_sack_rate_blend"], abs=1e-6)

    def test_fade_week2_blends_current_and_prior(self):
        """Week 2: base (current-season-only) differs from blend, which leans
        toward the prior season's rate but is not identical to it."""
        df = om.compute_season_to_date_features(_base_plays(), blend_n=4)
        r = _row(df, "AAA", 2021, 2)
        assert r["ol_sack_rate"] == pytest.approx(0.40, abs=1e-6)         # cum-only: 4/10
        assert r["ol_sack_rate_blend"] == pytest.approx(0.24, abs=1e-6)   # (4+8)/(10+40)

    def test_old_columns_untouched(self):
        """The pre-existing column is byte-identical to what the unmodified
        algorithm produces — current-season cumulative only, no prior season."""
        df = om.compute_season_to_date_features(_base_plays(), blend_n=4)
        r = _row(df, "AAA", 2021, 2)
        assert r["ol_sack_rate"] == pytest.approx(0.40, abs=1e-9)
        assert "ol_sack_rate_blend" in df.columns
        assert r["ol_sack_rate"] != pytest.approx(r["ol_sack_rate_blend"])

    def test_leakage_current_week_plays_do_not_affect_own_week(self):
        """Changing week 2's own plays must not change week 2's features —
        cum excludes the current week entirely."""
        df_a = om.compute_season_to_date_features(_base_plays(extra_2021_week2_aaa_sacks=5), blend_n=4)
        df_b = om.compute_season_to_date_features(_base_plays(extra_2021_week2_aaa_sacks=0), blend_n=4)
        ra, rb = _row(df_a, "AAA", 2021, 2), _row(df_b, "AAA", 2021, 2)
        assert ra["ol_sack_rate"] == pytest.approx(rb["ol_sack_rate"])
        assert ra["ol_sack_rate_blend"] == pytest.approx(rb["ol_sack_rate_blend"])

    def test_leakage_future_week_does_not_affect_past_weeks(self):
        """Adding an extreme week 3 must not change week 1 or week 2's values."""
        plays = _base_plays()
        df_before = om.compute_season_to_date_features(plays, blend_n=4)
        df_after = om.compute_season_to_date_features(_with_future_week3(plays), blend_n=4)
        for wk in (1, 2):
            b = _row(df_before, "AAA", 2021, wk)
            a = _row(df_after, "AAA", 2021, wk)
            assert a["ol_sack_rate"] == pytest.approx(b["ol_sack_rate"])
            assert a["ol_sack_rate_blend"] == pytest.approx(b["ol_sack_rate_blend"])

    def test_no_prior_season_uses_league_average(self):
        """2020 is the earliest season in the dataset — both teams' week-1
        blend falls back to the league-wide average of that same season,
        exactly as the existing cold start does."""
        df = om.compute_season_to_date_features(_base_plays(), blend_n=4)
        league_avg = (0.20 + 0.15) / 2  # AAA 4/20, BBB 3/20
        assert _row(df, "AAA", 2020, 1)["ol_sack_rate_blend"] == pytest.approx(league_avg, abs=1e-6)
        assert _row(df, "BBB", 2020, 1)["ol_sack_rate_blend"] == pytest.approx(league_avg, abs=1e-6)

    def test_prev_column_is_constant_across_the_season(self):
        """_prev carries the prior season's unblended value on every week —
        it does not fade like _blend does."""
        df = om.compute_season_to_date_features(_base_plays(), blend_n=4)
        w1 = _row(df, "AAA", 2021, 1)["ol_sack_rate_prev"]
        w2 = _row(df, "AAA", 2021, 2)["ol_sack_rate_prev"]
        assert w1 == pytest.approx(0.2, abs=1e-6)
        assert w2 == pytest.approx(0.2, abs=1e-6)

    def test_games_played_this_season(self):
        df = om.compute_season_to_date_features(_base_plays(), blend_n=4)
        assert _row(df, "AAA", 2021, 1)["games_played_this_season"] == 0
        assert _row(df, "AAA", 2021, 2)["games_played_this_season"] == 1

    def test_blend_n_is_a_parameter_not_a_constant(self):
        """Different N produces different blend values on the same input."""
        df_n2 = om.compute_season_to_date_features(_base_plays(), blend_n=2)
        df_n8 = om.compute_season_to_date_features(_base_plays(), blend_n=8)
        v2 = _row(df_n2, "AAA", 2021, 2)["ol_sack_rate_blend"]
        v8 = _row(df_n8, "AAA", 2021, 2)["ol_sack_rate_blend"]
        assert v2 != pytest.approx(v8)
        # N=2: (4 + 2*2)/(10 + 2*10) = 8/30
        assert v2 == pytest.approx(8 / 30, abs=1e-6)
        # N=8: (4 + 8*2)/(10 + 8*10) = 20/90
        assert v8 == pytest.approx(20 / 90, abs=1e-6)


# ── comprehensive: ratio-of-sums blend + cross-season FORM rolling ───────────


class TestComprehensiveBlend:
    def test_ratio_feature_week1_equals_cold_start(self):
        df = comp.compute_additional_team_features(_base_plays(), blend_n=4)
        r = _row(df, "AAA", 2021, 1)
        assert r["pass_explosive_rate_blend"] == pytest.approx(0.2, abs=1e-6)
        assert r["pass_explosive_rate"] == pytest.approx(r["pass_explosive_rate_blend"], abs=1e-6)

    def test_rolling_form_blend_reaches_into_prior_season(self):
        """
        Week 1 and week 2 of 2021 should incorporate 2020's last games,
        instead of resetting to NaN/cold-start the way the un-blended
        rolling_3wk_epa_trend does within a single season.

        AAA per-game off EPA: 2020wk1=0.1, 2020wk2=0.3, 2021wk1=0.5, 2021wk2=0.9
          2021 wk1 blend = mean(0.1, 0.3)      = 0.2   (last <=3 games before it)
          2021 wk2 blend = mean(0.1, 0.3, 0.5) = 0.3
        """
        df = comp.compute_additional_team_features(_base_plays(), blend_n=4)
        assert _row(df, "AAA", 2021, 1)["rolling_3wk_epa_trend_blend"] == pytest.approx(0.2, abs=1e-6)
        assert _row(df, "AAA", 2021, 2)["rolling_3wk_epa_trend_blend"] == pytest.approx(0.3, abs=1e-6)

    def test_rolling_form_blend_leading_nan_matches_cold_start_fallback(self):
        """A team's very first game in the whole dataset has no history at
        all; it falls back to the same league-average the cold start uses."""
        df = comp.compute_additional_team_features(_base_plays(), blend_n=4)
        r = _row(df, "AAA", 2020, 1)
        assert not np.isnan(r["rolling_3wk_epa_trend_blend"])
        assert r["rolling_3wk_epa_trend_blend"] == pytest.approx(r["rolling_3wk_epa_trend"], abs=1e-9)

    def test_old_columns_untouched(self):
        df = comp.compute_additional_team_features(_base_plays(), blend_n=4)
        r = _row(df, "AAA", 2021, 2)
        # cum-only (week 1's 0 explosive plays / 10 attempts) = 0.0
        assert r["pass_explosive_rate"] == pytest.approx(0.0, abs=1e-6)


# ── situational: game-count-based blend (win pct, avg margin) ───────────────


def _game(game_id, season, week, home, away, home_score, away_score, day):
    return dict(
        game_id=game_id, season=season, week=week,
        game_date=f"2020-01-{day:02d}" if season == 2020 else f"2021-01-{day:02d}",
        home_team=home, away_team=away,
        home_score=home_score, away_score=away_score,
    )


def _situational_games() -> pd.DataFrame:
    rows = [
        # 2020 (prior season): AAA goes 1-3 -> win_pct 0.25, avg margin -5.0
        _game("2020_01", 2020, 1, "AAA", "BBB", 10, 20, 1),   # AAA loses by 10
        _game("2020_02", 2020, 2, "AAA", "BBB", 10, 20, 8),   # AAA loses by 10
        _game("2020_03", 2020, 3, "BBB", "AAA", 20, 10, 15),  # AAA (away) loses by 10
        _game("2020_04", 2020, 4, "AAA", "BBB", 30, 20, 22),  # AAA wins by 10
        # 2021 (current season): AAA 1-0 heading into week 2
        _game("2021_01", 2021, 1, "AAA", "CCC", 20, 10, 1),   # AAA wins by 10
        _game("2021_02", 2021, 2, "AAA", "CCC", 15, 20, 8),   # AAA's own result — irrelevant to week 2's features
    ]
    return pd.DataFrame(rows)


class TestSituationalBlend:
    def test_season_win_pct_blend_matches_worked_example(self):
        """PROMPT §3c test 6: a 1-0 team at week 2 with a 0.25 prior and N=4
        gives (1 + 1.0) / 5 = 0.40."""
        df = situ.compute_situational_features(_situational_games(), blend_n=4)
        r = _row(df, "AAA", 2021, 2)
        assert r["season_win_pct_blend"] == pytest.approx(0.40, abs=1e-9)

    def test_avg_margin_blend_fade(self):
        """(margin_sum_through_prior + N*prior_avg_margin) / (games_played + N)
        = (10 + 4*(-5.0)) / (1 + 4) = -2.0"""
        df = situ.compute_situational_features(_situational_games(), blend_n=4)
        r = _row(df, "AAA", 2021, 2)
        assert r["avg_margin_blend"] == pytest.approx(-2.0, abs=1e-9)

    def test_week1_blend_equals_prior_season_value(self):
        """At week 1 (no current-season games yet), the blend reduces to the
        prior season's own full-season value — the game-count analogue of the
        rate features' week-1-equals-cold-start property. Note this is NOT
        the same as the existing flat 0.5 cold start for season_win_pct,
        which ignores the prior season entirely; the blended version
        deliberately uses the real prior value, matching the treatment table."""
        df = situ.compute_situational_features(_situational_games(), blend_n=4)
        r = _row(df, "AAA", 2021, 1)
        assert r["season_win_pct_blend"] == pytest.approx(0.25, abs=1e-9)
        assert r["avg_margin_blend"] == pytest.approx(-5.0, abs=1e-9)

    def test_prev_columns_are_constant_across_the_season(self):
        df = situ.compute_situational_features(_situational_games(), blend_n=4)
        w1 = _row(df, "AAA", 2021, 1)
        w2 = _row(df, "AAA", 2021, 2)
        assert w1["season_win_pct_prev"] == pytest.approx(0.25, abs=1e-9)
        assert w2["season_win_pct_prev"] == pytest.approx(0.25, abs=1e-9)
        assert w1["prior_week_margin_prev"] == pytest.approx(-5.0, abs=1e-9)
        assert w2["prior_week_margin_prev"] == pytest.approx(-5.0, abs=1e-9)

    def test_rest_days_has_no_blend_column(self):
        """rest_days is schedule-derived, not a performance stat — no blend."""
        assert "rest_days_blend" not in situ.SITUATIONAL_FEATURES_BLEND
        df = situ.compute_situational_features(_situational_games(), blend_n=4)
        assert "rest_days_blend" not in df.columns

    def test_old_columns_untouched(self):
        df = situ.compute_situational_features(_situational_games(), blend_n=4)
        r = _row(df, "AAA", 2021, 2)
        assert r["season_win_pct"] == pytest.approx(1.0, abs=1e-9)  # 1-0 cum, unblended


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

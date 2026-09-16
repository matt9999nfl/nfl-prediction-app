"""
Comprehensive v2 feature computation — additional play-based team metrics.

Adds to the base OL features from features.ol_metrics:

    QB / Passing efficiency (per team, season-to-date):
        qb_cpoe                      — mean CPOE on pass attempts (non-null only)
        qb_epa_under_pressure        — mean EPA on plays where qb_hit=1 OR sack=1
        pass_explosive_rate          — % of pass plays gaining >= 20 yards

    OL run-blocking (new):
        rush_explosive_rate          — % of rush plays gaining >= 10 yards

    Defense — allowed rates (per team, season-to-date):
        def_epa_per_play             — mean EPA allowed per play (all play types)
        def_explosive_pass_allowed_rate — % of opp pass plays allowing >= 20 yards
        def_explosive_rush_allowed_rate — % of opp rush plays allowing >= 10 yards

    Form:
        rolling_3wk_epa_trend        — mean team offensive EPA/play over last 3 games
                                       (shift-1 rolling window; excludes current week)

All features are season-to-date through week W-1. Week 1 cold-start is filled
with prior-season full-season averages; teams with no prior season use the
league-wide average for the earliest available season.

Minimum sample threshold: >= 20 qualifying plays before trusting a rate.
Below-threshold values are set to NaN and will be imputed during model training.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MIN_PLAY_SAMPLE = 20
_EPS = 1e-9

# ── Feature name lists ─────────────────────────────────────────────────────────

QB_FEATURES = [
    "qb_cpoe",
    "qb_epa_under_pressure",
    "pass_explosive_rate",
]
NEW_RUN_FEATURES = [
    "rush_explosive_rate",
]
NEW_DEF_FEATURES = [
    "def_epa_per_play",
    "def_explosive_pass_allowed_rate",
    "def_explosive_rush_allowed_rate",
]
FORM_FEATURES = [
    "rolling_3wk_epa_trend",
]

ALL_ADDITIONAL_TEAM_FEATURES = (
    QB_FEATURES
    + NEW_RUN_FEATURES
    + NEW_DEF_FEATURES
    + FORM_FEATURES
)


# ── Per-game aggregates ────────────────────────────────────────────────────────

def _per_game_qb_off(plays: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns three DataFrames per (team, season, week):
      - base: pass_att_v2, pass_explosive_count
      - pressure: pressure_play_count, pressure_epa_sum
      - cpoe: cpoe_sum, cpoe_count
    """
    p = plays[(plays["play_type"] == "pass") & plays["down"].notna()].copy()
    p["sack"]   = p["sack"].fillna(0).astype(int)
    p["qb_hit"] = p["qb_hit"].fillna(0).astype(int)
    p["is_explosive"] = (p["yards_gained"] >= 20).astype(int)
    p["is_pressure"]  = ((p["qb_hit"] == 1) | (p["sack"] == 1)).astype(int)

    base = (
        p.groupby(["posteam", "season", "week"])
        .agg(
            pass_att_v2=("epa", "count"),
            pass_explosive_count=("is_explosive", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )

    pressure = (
        p[p["is_pressure"] == 1]
        .groupby(["posteam", "season", "week"])
        .agg(
            pressure_play_count=("epa", "count"),
            pressure_epa_sum=("epa", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )

    # cpoe only valid on plays where the model produced an estimate
    cpoe_valid = p.dropna(subset=["cpoe"])
    cpoe = (
        cpoe_valid
        .groupby(["posteam", "season", "week"])
        .agg(
            cpoe_sum=("cpoe", "sum"),
            cpoe_count=("cpoe", "count"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )

    return base, pressure, cpoe


def _per_game_run_explosive(plays: pd.DataFrame) -> pd.DataFrame:
    """Rush att and explosive rush count per (team, season, week)."""
    r = plays[(plays["play_type"] == "run") & plays["down"].notna()].copy()
    r["is_explosive"] = (r["yards_gained"] >= 10).astype(int)
    return (
        r.groupby(["posteam", "season", "week"])
        .agg(
            rush_att_v2=("epa", "count"),
            rush_explosive_count=("is_explosive", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )


def _per_game_def_comprehensive(plays: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns three DataFrames per (defteam, season, week):
      - all_plays: def_total_play_count, def_total_epa_sum
      - pass_expl: def_pass_att_v2, def_pass_explosive_count
      - run_expl:  def_rush_att_v2, def_rush_explosive_count
    """
    valid = plays[plays["defteam"].notna() & plays["down"].notna()].copy()

    all_plays = (
        valid.groupby(["defteam", "season", "week"])
        .agg(
            def_total_play_count=("epa", "count"),
            def_total_epa_sum=("epa", "sum"),
        )
        .reset_index()
        .rename(columns={"defteam": "team"})
    )

    pass_plays = valid[valid["play_type"] == "pass"].copy()
    pass_plays["is_explosive"] = (pass_plays["yards_gained"] >= 20).astype(int)
    pass_expl = (
        pass_plays.groupby(["defteam", "season", "week"])
        .agg(
            def_pass_att_v2=("epa", "count"),
            def_pass_explosive_count=("is_explosive", "sum"),
        )
        .reset_index()
        .rename(columns={"defteam": "team"})
    )

    run_plays = valid[valid["play_type"] == "run"].copy()
    run_plays["is_explosive"] = (run_plays["yards_gained"] >= 10).astype(int)
    run_expl = (
        run_plays.groupby(["defteam", "season", "week"])
        .agg(
            def_rush_att_v2=("epa", "count"),
            def_rush_explosive_count=("is_explosive", "sum"),
        )
        .reset_index()
        .rename(columns={"defteam": "team"})
    )

    return all_plays, pass_expl, run_expl


def _per_game_off_all(plays: pd.DataFrame) -> pd.DataFrame:
    """Offensive all-play EPA and count per (team, season, week) — used for rolling trend."""
    valid = plays[
        plays["posteam"].notna()
        & plays["down"].notna()
        & plays["play_type"].isin(["pass", "run"])
    ].copy()
    return (
        valid.groupby(["posteam", "season", "week"])
        .agg(
            off_all_play_count=("epa", "count"),
            off_all_epa_sum=("epa", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )


# ── Season-to-date computation ─────────────────────────────────────────────────

RAW_ADDL_COUNT_COLS = [
    "pass_att_v2", "pass_explosive_count",
    "pressure_play_count", "pressure_epa_sum",
    "cpoe_sum", "cpoe_count",
    "rush_att_v2", "rush_explosive_count",
    "def_total_play_count", "def_total_epa_sum",
    "def_pass_att_v2", "def_pass_explosive_count",
    "def_rush_att_v2", "def_rush_explosive_count",
]


def compute_additional_team_features(plays: pd.DataFrame, blend_n: int = 4) -> pd.DataFrame:
    """
    Compute comprehensive v2 season-to-date team features from plays.

    Returns a DataFrame keyed by (team, season, week) with all features
    in ALL_ADDITIONAL_TEAM_FEATURES reflecting data through week W-1, plus
    `_blend` (prior season as `blend_n` pseudo-games) and `_prev` (prior
    season's unblended full-season value) counterparts — see
    PROMPT-PRIOR-SEASON-BLEND.md §3a/§3b.

    Requires plays to contain: posteam, defteam, season, week, play_type,
    down, epa, yards_gained, sack, qb_hit, cpoe
    """
    logger.info("Computing comprehensive v2 team features ...")

    # ── Per-game aggregates ────────────────────────────────────────────────
    logger.info("  Building per-game QB/explosive/def aggregates ...")
    qb_base, qb_pressure, qb_cpoe = _per_game_qb_off(plays)
    run_expl    = _per_game_run_explosive(plays)
    def_all, def_pass_expl, def_run_expl = _per_game_def_comprehensive(plays)
    off_all     = _per_game_off_all(plays)

    # ── Team-week universe (same as ol_metrics) ───────────────────────────
    off_teams = plays[plays["play_type"].isin(["pass", "run"])][
        ["season", "week", "posteam"]
    ].drop_duplicates().rename(columns={"posteam": "team"})
    def_teams = plays[plays["play_type"].isin(["pass", "run"])][
        ["season", "week", "defteam"]
    ].drop_duplicates().rename(columns={"defteam": "team"})
    all_team_weeks = (
        pd.concat([off_teams, def_teams])
        .drop_duplicates()
        .sort_values(["team", "season", "week"])
        .reset_index(drop=True)
    )

    # ── Merge per-game stats ───────────────────────────────────────────────
    df = all_team_weeks.copy()
    for src in [qb_base, qb_pressure, qb_cpoe, run_expl,
                def_all, def_pass_expl, def_run_expl]:
        df = df.merge(src, on=["team", "season", "week"], how="left")

    for col in RAW_ADDL_COUNT_COLS:
        df[col] = df[col].fillna(0.0)

    # ── Store per-game all-play offensive EPA for rolling trend ───────────
    df = df.merge(off_all, on=["team", "season", "week"], how="left")
    df["off_all_play_count"] = df["off_all_play_count"].fillna(0.0)
    df["off_all_epa_sum"]    = df["off_all_epa_sum"].fillna(0.0)
    # Per-game EPA per play (this week's raw value)
    df["off_epa_per_play_raw"] = (
        df["off_all_epa_sum"]
        / df["off_all_play_count"].clip(lower=1)
    )

    # ── Cumulative season-to-date sums (exclude current week) ─────────────
    logger.info("  Computing cumulative v2 season-to-date sums ...")
    df = df.sort_values(["team", "season", "week"]).reset_index(drop=True)

    for col in RAW_ADDL_COUNT_COLS:
        cum = df.groupby(["team", "season"])[col].cumsum()
        df[f"{col}_cum"] = cum - df[col]

    # ── Rate features ──────────────────────────────────────────────────────

    # qb_cpoe: mean CPOE (only reliable with enough plays)
    df["qb_cpoe"] = df["cpoe_sum_cum"] / (df["cpoe_count_cum"] + _EPS)
    df.loc[df["cpoe_count_cum"] < MIN_PLAY_SAMPLE, "qb_cpoe"] = np.nan

    # qb_epa_under_pressure
    df["qb_epa_under_pressure"] = (
        df["pressure_epa_sum_cum"] / (df["pressure_play_count_cum"] + _EPS)
    )
    df.loc[df["pressure_play_count_cum"] < MIN_PLAY_SAMPLE, "qb_epa_under_pressure"] = np.nan

    # pass_explosive_rate
    df["pass_explosive_rate"] = (
        df["pass_explosive_count_cum"] / (df["pass_att_v2_cum"] + _EPS)
    )

    # rush_explosive_rate
    df["rush_explosive_rate"] = (
        df["rush_explosive_count_cum"] / (df["rush_att_v2_cum"] + _EPS)
    )

    # def_epa_per_play
    df["def_epa_per_play"] = (
        df["def_total_epa_sum_cum"] / (df["def_total_play_count_cum"] + _EPS)
    )

    # def_explosive_pass_allowed_rate
    df["def_explosive_pass_allowed_rate"] = (
        df["def_pass_explosive_count_cum"] / (df["def_pass_att_v2_cum"] + _EPS)
    )

    # def_explosive_rush_allowed_rate
    df["def_explosive_rush_allowed_rate"] = (
        df["def_rush_explosive_count_cum"] / (df["def_rush_att_v2_cum"] + _EPS)
    )

    # ── Rolling 3-week EPA trend ───────────────────────────────────────────
    # shift(1) to exclude current week; rolling(3) over prior 3 completed games
    # within the current season only (Week 1 = NaN, filled by cold-start below)
    logger.info("  Computing rolling 3-week EPA trend ...")
    df["rolling_3wk_epa_trend"] = (
        df.groupby(["team", "season"])["off_epa_per_play_raw"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )

    # rolling_3wk_epa_trend_blend: same rolling window, but grouped by team
    # only (not team+season), so at week 1-2 of a season the window reaches
    # back into the prior season's final games instead of resetting to NaN.
    # df is sorted ["team","season","week"], which is chronological order
    # within a team across season boundaries (REG seasons only), so this is
    # still leakage-safe: week W only ever sees weeks < W of season S and any
    # week of S-1. Only a team's very first game in the whole dataset (2015
    # week 1) has no history to look back on; that NaN is filled below with
    # the same league-wide average the cold start fill uses.
    df["rolling_3wk_epa_trend_blend"] = (
        df.groupby("team")["off_epa_per_play_raw"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )

    # ── Week 1 cold-start fill ─────────────────────────────────────────────
    df = _fill_week1_cold_start(df)

    # ── Prior-season-blended features (new columns; old ones untouched) ────
    df = _add_blended_additional_features(df, blend_n)

    # ── Separate prior-season features (selectable, not blended) ───────────
    df = _add_prev_season_additional_features(df)

    logger.info(
        f"  Additional features built: {len(ALL_ADDITIONAL_TEAM_FEATURES)} features "
        f"for {df['team'].nunique()} teams, "
        f"{df['season'].nunique()} seasons"
    )
    return df


# ── Week-1 cold-start helpers ──────────────────────────────────────────────────

def _compute_full_season_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute each team's full-season averages of ALL_ADDITIONAL_TEAM_FEATURES
    from the per-game raw count data (before cumsum).

    We use the raw per-game counts (not the cumulative columns) so we can
    sum directly across all weeks of the season.
    """
    _eps = _EPS

    season_totals = df.groupby(["team", "season"]).agg(
        # QB / pass
        t_pass_att_v2=("pass_att_v2", "sum"),
        t_pass_explosive_count=("pass_explosive_count", "sum"),
        t_pressure_play_count=("pressure_play_count", "sum"),
        t_pressure_epa_sum=("pressure_epa_sum", "sum"),
        t_cpoe_sum=("cpoe_sum", "sum"),
        t_cpoe_count=("cpoe_count", "sum"),
        # Run
        t_rush_att_v2=("rush_att_v2", "sum"),
        t_rush_explosive_count=("rush_explosive_count", "sum"),
        # Defense
        t_def_total_play_count=("def_total_play_count", "sum"),
        t_def_total_epa_sum=("def_total_epa_sum", "sum"),
        t_def_pass_att_v2=("def_pass_att_v2", "sum"),
        t_def_pass_explosive_count=("def_pass_explosive_count", "sum"),
        t_def_rush_att_v2=("def_rush_att_v2", "sum"),
        t_def_rush_explosive_count=("def_rush_explosive_count", "sum"),
        # For rolling trend: full-season mean EPA per play
        t_off_all_play_count=("off_all_play_count", "sum"),
        t_off_all_epa_sum=("off_all_epa_sum", "sum"),
    ).reset_index()

    avgs = season_totals[["team", "season"]].copy()

    avgs["qb_cpoe"] = (
        season_totals["t_cpoe_sum"]
        / (season_totals["t_cpoe_count"] + _eps)
    )
    avgs.loc[season_totals["t_cpoe_count"] < MIN_PLAY_SAMPLE, "qb_cpoe"] = np.nan

    avgs["qb_epa_under_pressure"] = (
        season_totals["t_pressure_epa_sum"]
        / (season_totals["t_pressure_play_count"] + _eps)
    )
    avgs.loc[season_totals["t_pressure_play_count"] < MIN_PLAY_SAMPLE, "qb_epa_under_pressure"] = np.nan

    avgs["pass_explosive_rate"] = (
        season_totals["t_pass_explosive_count"]
        / (season_totals["t_pass_att_v2"] + _eps)
    )
    avgs["rush_explosive_rate"] = (
        season_totals["t_rush_explosive_count"]
        / (season_totals["t_rush_att_v2"] + _eps)
    )
    avgs["def_epa_per_play"] = (
        season_totals["t_def_total_epa_sum"]
        / (season_totals["t_def_total_play_count"] + _eps)
    )
    avgs["def_explosive_pass_allowed_rate"] = (
        season_totals["t_def_pass_explosive_count"]
        / (season_totals["t_def_pass_att_v2"] + _eps)
    )
    avgs["def_explosive_rush_allowed_rate"] = (
        season_totals["t_def_rush_explosive_count"]
        / (season_totals["t_def_rush_att_v2"] + _eps)
    )
    avgs["rolling_3wk_epa_trend"] = (
        season_totals["t_off_all_epa_sum"]
        / (season_totals["t_off_all_play_count"].clip(lower=1))
    )

    # Raw totals, exposed (additive only) so blended (prior-N-games) features
    # can scale them without recomputing per-game aggregates from scratch.
    _RAW_TOTAL_RENAME = {
        "t_pass_att_v2": "pass_att_v2_total",
        "t_pass_explosive_count": "pass_explosive_count_total",
        "t_pressure_play_count": "pressure_play_count_total",
        "t_pressure_epa_sum": "pressure_epa_sum_total",
        "t_cpoe_sum": "cpoe_sum_total",
        "t_cpoe_count": "cpoe_count_total",
        "t_rush_att_v2": "rush_att_v2_total",
        "t_rush_explosive_count": "rush_explosive_count_total",
        "t_def_total_play_count": "def_total_play_count_total",
        "t_def_total_epa_sum": "def_total_epa_sum_total",
        "t_def_pass_att_v2": "def_pass_att_v2_total",
        "t_def_pass_explosive_count": "def_pass_explosive_count_total",
        "t_def_rush_att_v2": "def_rush_att_v2_total",
        "t_def_rush_explosive_count": "def_rush_explosive_count_total",
    }
    for src, dst in _RAW_TOTAL_RENAME.items():
        avgs[dst] = season_totals[src].values

    games_played = df.groupby(["team", "season"])["week"].nunique()
    avgs["games_played"] = avgs.set_index(["team", "season"]).index.map(games_played).values

    return avgs.reset_index(drop=True)


def _fill_week1_cold_start(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace Week-1 values of ALL_ADDITIONAL_TEAM_FEATURES with prior-season
    full-season averages. Uses a vectorized merge approach (O(n) per feature).

    Teams/features with no prior-season data fall back to the league average
    of the earliest available season.
    """
    season_avgs = _compute_full_season_averages(df)

    # Shift season +1 to create a "prior season → this season" lookup
    prior_lookup = season_avgs.copy()
    prior_lookup["season"] = prior_lookup["season"] + 1

    # League average fallback: mean across all teams in earliest season
    earliest = season_avgs["season"].min()
    league_avg = (
        season_avgs[season_avgs["season"] == earliest]
        [ALL_ADDITIONAL_TEAM_FEATURES]
        .mean()
    )

    week1_mask = df["week"] == 1
    if week1_mask.sum() == 0:
        return df

    df = df.copy()
    week1_rows = df.loc[week1_mask, ["team", "season"]].copy()

    # Vectorized join for all features at once
    merged = week1_rows.merge(
        prior_lookup[["team", "season"] + ALL_ADDITIONAL_TEAM_FEATURES],
        on=["team", "season"],
        how="left",
    )
    for feat in ALL_ADDITIONAL_TEAM_FEATURES:
        filled = merged[feat].fillna(league_avg.get(feat, np.nan))
        df.loc[week1_mask, feat] = filled.values

    return df


# ── Prior-season blend (new columns; see PROMPT-PRIOR-SEASON-BLEND.md §3a) ───
#
# All seven QB/RUN/DEF features here are ratios of sums, so they take the
# count-based blend. FORM (rolling_3wk_epa_trend) is handled separately above
# by extending the rolling window across the season boundary instead.
_ADDL_BLEND_DEFS: dict[str, tuple[str, str, str, str]] = {
    # feature -> (numerator_cum_col, denominator_cum_col, numerator_total_col, denominator_total_col)
    "qb_cpoe":                         ("cpoe_sum_cum", "cpoe_count_cum",
                                         "cpoe_sum_total", "cpoe_count_total"),
    "qb_epa_under_pressure":           ("pressure_epa_sum_cum", "pressure_play_count_cum",
                                         "pressure_epa_sum_total", "pressure_play_count_total"),
    "pass_explosive_rate":             ("pass_explosive_count_cum", "pass_att_v2_cum",
                                         "pass_explosive_count_total", "pass_att_v2_total"),
    "rush_explosive_rate":             ("rush_explosive_count_cum", "rush_att_v2_cum",
                                         "rush_explosive_count_total", "rush_att_v2_total"),
    "def_epa_per_play":                ("def_total_epa_sum_cum", "def_total_play_count_cum",
                                         "def_total_epa_sum_total", "def_total_play_count_total"),
    "def_explosive_pass_allowed_rate": ("def_pass_explosive_count_cum", "def_pass_att_v2_cum",
                                         "def_pass_explosive_count_total", "def_pass_att_v2_total"),
    "def_explosive_rush_allowed_rate": ("def_rush_explosive_count_cum", "def_rush_att_v2_cum",
                                         "def_rush_explosive_count_total", "def_rush_att_v2_total"),
}

ALL_ADDITIONAL_TEAM_FEATURES_BLEND = [f"{f}_blend" for f in ALL_ADDITIONAL_TEAM_FEATURES]
ALL_ADDITIONAL_TEAM_FEATURES_PREV  = [f"{f}_prev"  for f in ALL_ADDITIONAL_TEAM_FEATURES]


def _add_blended_additional_features(df: pd.DataFrame, N: int) -> pd.DataFrame:
    """
    Add `<feature>_blend` columns for the seven count-based ratios, plus fill
    the handful of leading NaNs left in rolling_3wk_epa_trend_blend (a team's
    very first game in the whole dataset — see the comment where that column
    is computed) with the league-wide average, same fallback the cold start
    uses. See _add_blended_rate_features in ol_metrics.py for the identical
    mechanics on the base 12 features.
    """
    df = df.copy()
    season_totals = _compute_full_season_averages(df)
    total_cols = [c for c in season_totals.columns if c.endswith("_total")]

    prior_lookup = season_totals.copy()
    prior_lookup["season"] = prior_lookup["season"] + 1
    prior_lookup = prior_lookup.rename(columns={c: f"prior_{c}" for c in total_cols})
    prior_lookup = prior_lookup.rename(columns={"games_played": "prior_games_played"})
    prior_lookup = prior_lookup[["team", "season", "prior_games_played"] + [f"prior_{c}" for c in total_cols]]

    earliest = season_totals["season"].min()
    early = season_totals[season_totals["season"] == earliest]
    league_avg_rate = early[ALL_ADDITIONAL_TEAM_FEATURES].mean()
    league_den_pg = (early[total_cols].div(early["games_played"], axis=0)).mean()

    df = df.merge(prior_lookup, on=["team", "season"], how="left")
    has_prior = df["prior_games_played"].notna() & (df["prior_games_played"] > 0)

    for feat, (num_cum, den_cum, num_total, den_total) in _ADDL_BLEND_DEFS.items():
        prior_games = df["prior_games_played"]
        prior_den_pg = np.where(
            has_prior, df[f"prior_{den_total}"] / prior_games, league_den_pg[den_total]
        )
        prior_num_pg = np.where(
            has_prior,
            df[f"prior_{num_total}"] / prior_games,
            league_avg_rate[feat] * league_den_pg[den_total],
        )
        blended_num = df[num_cum] + N * prior_num_pg
        blended_den = df[den_cum] + N * prior_den_pg
        df[f"{feat}_blend"] = blended_num / (blended_den + _EPS)

    df = df.drop(columns=["prior_games_played"] + [f"prior_{c}" for c in total_cols])

    # rolling_3wk_epa_trend_blend: fill the leading NaNs (each team's first
    # game in the dataset — no prior season to look back on at all).
    league_form = league_avg_rate["rolling_3wk_epa_trend"]
    df["rolling_3wk_epa_trend_blend"] = df["rolling_3wk_epa_trend_blend"].fillna(league_form)

    return df


def _add_prev_season_additional_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add `<feature>_prev` columns: the prior season's full-season value,
    unblended, carried on every week of season S — see the identical helper
    in ol_metrics.py for the rationale (capability-gap closure, PROMPT §3b).
    """
    df = df.copy()
    season_avgs = _compute_full_season_averages(df)

    prior_lookup = season_avgs.copy()
    prior_lookup["season"] = prior_lookup["season"] + 1

    earliest = season_avgs["season"].min()
    league_avg = season_avgs[season_avgs["season"] == earliest][ALL_ADDITIONAL_TEAM_FEATURES].mean()

    merged = df[["team", "season"]].merge(
        prior_lookup[["team", "season"] + ALL_ADDITIONAL_TEAM_FEATURES],
        on=["team", "season"], how="left",
    )
    for feat in ALL_ADDITIONAL_TEAM_FEATURES:
        df[f"{feat}_prev"] = merged[feat].fillna(league_avg[feat]).values
    return df

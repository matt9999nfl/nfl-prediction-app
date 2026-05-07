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


def compute_additional_team_features(plays: pd.DataFrame) -> pd.DataFrame:
    """
    Compute comprehensive v2 season-to-date team features from plays.

    Returns a DataFrame keyed by (team, season, week) with all features
    in ALL_ADDITIONAL_TEAM_FEATURES reflecting data through week W-1.

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

    # ── Week 1 cold-start fill ─────────────────────────────────────────────
    df = _fill_week1_cold_start(df)

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

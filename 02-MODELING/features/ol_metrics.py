"""
OL and defensive feature computation from curated.plays / curated.games.

Core guarantee
--------------
Features for (team, season, week=W) reflect ONLY plays from weeks 1..(W-1)
of that season.  No look-ahead leakage of any kind.

Week 1 cold-start
-----------------
At Week 1 the season-to-date window is empty.  We substitute the team's
full-season average from the prior season (season - 1).

Special cases
-------------
- 2015 Week 1: no 2014 data exists.  We fill with the 2015 league-wide
  average (computed across all teams).  These games appear only in training
  folds, never in a test fold, so the substitution cannot contaminate OOS
  evaluation.
- A team with < 20 qualifying plays in the cumulative window is flagged via
  *_sufficient = False.  Features are still computed but the flag lets
  downstream models or reports treat these values with caution.
- qb_scramble is NOT in curated.plays; scramble_rate is omitted per spec.

Feature names
-------------
All features are named by what they measure, not by data source.
Offensive (posteam perspective):
    ol_sack_rate, ol_qb_hit_rate, ol_pressure_proxy_rate,
    ol_pass_epa_per_att, ol_rush_epa_per_att, ol_rush_yards_per_att

Defensive (defteam perspective):
    def_sack_rate, def_qb_hit_rate, def_pressure_proxy_rate,
    def_pass_epa_allowed_per_att, def_rush_epa_allowed_per_att,
    def_rush_yards_allowed_per_att
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from google.cloud import bigquery

logger = logging.getLogger(__name__)

PROJECT = "nfl-model-471509"
MIN_PLAY_SAMPLE = 20  # minimum plays before trusting a rate

# ── Feature name lists ──────────────────────────────────────────────────────

PASS_OL_FEATURES = [
    "ol_sack_rate",
    "ol_qb_hit_rate",
    "ol_pressure_proxy_rate",
    "ol_pass_epa_per_att",
]
RUN_OL_FEATURES = [
    "ol_rush_epa_per_att",
    "ol_rush_yards_per_att",
]
OL_FEATURES = PASS_OL_FEATURES + RUN_OL_FEATURES

DEF_FEATURES = [
    "def_sack_rate",
    "def_qb_hit_rate",
    "def_pressure_proxy_rate",
    "def_pass_epa_allowed_per_att",
    "def_rush_epa_allowed_per_att",
    "def_rush_yards_allowed_per_att",
]

ALL_TEAM_RATE_FEATURES = OL_FEATURES + DEF_FEATURES

GAME_CONTEXT_FEATURES = [
    "home_advantage",
    "div_game",
    "roof_dome",
    "temp",
    "wind",
]

# Column name mapping: home/away prefix applied when building the game matrix
def prefixed(prefix: str, cols: list[str]) -> list[str]:
    return [f"{prefix}_{c}" for c in cols]

HOME_FEATURES = prefixed("home", ALL_TEAM_RATE_FEATURES)
AWAY_FEATURES = prefixed("away", ALL_TEAM_RATE_FEATURES)
ALL_MODEL_FEATURES = HOME_FEATURES + AWAY_FEATURES + GAME_CONTEXT_FEATURES


# ── Data loading ────────────────────────────────────────────────────────────

def load_plays(client: bigquery.Client) -> pd.DataFrame:
    """Load curated.plays (all seasons).  Returns ~500 k rows."""
    q = """
    SELECT
        game_id,
        season,
        week,
        posteam,
        defteam,
        play_type,
        down,
        sack,
        qb_hit,
        epa,
        yards_gained,
        cpoe
    FROM `nfl-model-471509.curated.plays`
    ORDER BY season, week, game_id
    """
    logger.info("Loading curated.plays …")
    df = client.query(q).to_dataframe()
    logger.info(f"  {len(df):,} plays loaded")
    return df


def load_games(client: bigquery.Client) -> pd.DataFrame:
    """Load curated.games (all REG season games)."""
    q = """
    SELECT
        game_id,
        season,
        week,
        game_date,
        home_team,
        away_team,
        home_score,
        away_score,
        home_spread_close,
        total_close,
        home_covered,
        roof,
        div_game,
        temp,
        wind
    FROM `nfl-model-471509.curated.games`
    ORDER BY season, week, game_id
    """
    logger.info("Loading curated.games …")
    df = client.query(q).to_dataframe()
    logger.info(f"  {len(df):,} games loaded")
    return df


# ── Per-game team aggregates ─────────────────────────────────────────────────

def _per_game_pass_off(plays: pd.DataFrame) -> pd.DataFrame:
    """Offensive pass stats per (team, season, week)."""
    p = plays[
        (plays["play_type"] == "pass") & plays["down"].notna()
    ].copy()
    p["sack"] = p["sack"].astype(int)
    p["qb_hit"] = p["qb_hit"].astype(int)
    return (
        p.groupby(["posteam", "season", "week"])
        .agg(
            pass_att=("play_type", "count"),
            sacks=("sack", "sum"),
            qb_hits=("qb_hit", "sum"),
            pass_epa_sum=("epa", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )


def _per_game_run_off(plays: pd.DataFrame) -> pd.DataFrame:
    """Offensive run stats per (team, season, week)."""
    r = plays[
        (plays["play_type"] == "run") & plays["down"].notna()
    ].copy()
    return (
        r.groupby(["posteam", "season", "week"])
        .agg(
            rush_att=("play_type", "count"),
            rush_epa_sum=("epa", "sum"),
            rush_yards_sum=("yards_gained", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )


def _per_game_pass_def(plays: pd.DataFrame) -> pd.DataFrame:
    """Defensive pass stats per (team, season, week)."""
    p = plays[
        (plays["play_type"] == "pass") & plays["down"].notna()
    ].copy()
    p["sack"] = p["sack"].astype(int)
    p["qb_hit"] = p["qb_hit"].astype(int)
    return (
        p.groupby(["defteam", "season", "week"])
        .agg(
            def_pass_att=("play_type", "count"),
            def_sacks=("sack", "sum"),
            def_qb_hits=("qb_hit", "sum"),
            def_pass_epa_sum=("epa", "sum"),
        )
        .reset_index()
        .rename(columns={"defteam": "team"})
    )


def _per_game_run_def(plays: pd.DataFrame) -> pd.DataFrame:
    """Defensive run stats per (team, season, week)."""
    r = plays[
        (plays["play_type"] == "run") & plays["down"].notna()
    ].copy()
    return (
        r.groupby(["defteam", "season", "week"])
        .agg(
            def_rush_att=("play_type", "count"),
            def_rush_epa_sum=("epa", "sum"),
            def_rush_yards_sum=("yards_gained", "sum"),
        )
        .reset_index()
        .rename(columns={"defteam": "team"})
    )


# ── Season-to-date rolling features ─────────────────────────────────────────

RAW_COUNT_COLS = [
    "pass_att", "sacks", "qb_hits", "pass_epa_sum",
    "rush_att", "rush_epa_sum", "rush_yards_sum",
    "def_pass_att", "def_sacks", "def_qb_hits", "def_pass_epa_sum",
    "def_rush_att", "def_rush_epa_sum", "def_rush_yards_sum",
]


def compute_season_to_date_features(plays: pd.DataFrame, blend_n: int = 4) -> pd.DataFrame:
    """
    Returns a DataFrame keyed by (team, season, week) containing season-to-date
    OL and defensive rate features through week-1 of that week.

    Steps:
      1. Build per-game aggregates for all four stat groups
      2. Merge into one row per (team, season, week)
      3. Cumulative sum within each (team, season), shifted back by one game
         (i.e., exclude the current week from the window)
      4. Compute rate features from cumulative counts
      5. Fill Week 1 gaps with prior-season full-season averages
      6. Set sample-size sufficiency flags
      7. Add `_blend` columns: prior season enters as `blend_n` pseudo-games,
         fading as the current season accumulates (see _add_blended_rate_features)
      8. Add `_prev` columns: the prior season's full-season value, unblended,
         carried on every week (not just week 1) — see _add_prev_season_features
      9. Add games_played_this_season, the count of this team's own games
         played before the current week (byes do not count)

    `blend_n` is a parameter, not a constant, so callers can sweep it in a
    backtest. It has no effect on any column that existed before this feature
    (those are computed in steps 1-6, untouched by 7-9).
    """
    logger.info("Computing per-game team aggregates …")
    off_pass = _per_game_pass_off(plays)
    off_run  = _per_game_run_off(plays)
    def_pass = _per_game_pass_def(plays)
    def_run  = _per_game_run_def(plays)

    # Universe of (team, season, week) from play-by-play
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

    # Merge all four stat groups
    df = all_team_weeks.copy()
    for src in [off_pass, off_run, def_pass, def_run]:
        df = df.merge(src, on=["team", "season", "week"], how="left")

    # Fill missing counts with 0 (team appeared on one side but not other — rare)
    for col in RAW_COUNT_COLS:
        df[col] = df[col].fillna(0.0)

    # Cumulative season-to-date sums, EXCLUDING the current week
    logger.info("Computing cumulative season-to-date sums …")
    df = df.sort_values(["team", "season", "week"]).reset_index(drop=True)
    for col in RAW_COUNT_COLS:
        cum = df.groupby(["team", "season"])[col].cumsum()
        df[f"{col}_cum"] = cum - df[col]   # subtract current week → prior weeks only

    # Rate features (safe division; eps avoids /0 for Week 1 before cold-start fill)
    _eps = 1e-9
    df["ol_sack_rate"]               = df["sacks_cum"]      / (df["pass_att_cum"] + _eps)
    df["ol_qb_hit_rate"]             = df["qb_hits_cum"]    / (df["pass_att_cum"] + _eps)
    df["ol_pressure_proxy_rate"]     = (df["sacks_cum"] + df["qb_hits_cum"]) / (df["pass_att_cum"] + _eps)
    df["ol_pass_epa_per_att"]        = df["pass_epa_sum_cum"] / (df["pass_att_cum"] + _eps)
    df["ol_rush_epa_per_att"]        = df["rush_epa_sum_cum"] / (df["rush_att_cum"] + _eps)
    df["ol_rush_yards_per_att"]      = df["rush_yards_sum_cum"] / (df["rush_att_cum"] + _eps)

    df["def_sack_rate"]              = df["def_sacks_cum"]     / (df["def_pass_att_cum"] + _eps)
    df["def_qb_hit_rate"]            = df["def_qb_hits_cum"]   / (df["def_pass_att_cum"] + _eps)
    df["def_pressure_proxy_rate"]    = (df["def_sacks_cum"] + df["def_qb_hits_cum"]) / (df["def_pass_att_cum"] + _eps)
    df["def_pass_epa_allowed_per_att"]   = df["def_pass_epa_sum_cum"]  / (df["def_pass_att_cum"]  + _eps)
    df["def_rush_epa_allowed_per_att"]   = df["def_rush_epa_sum_cum"]  / (df["def_rush_att_cum"]  + _eps)
    df["def_rush_yards_allowed_per_att"] = df["def_rush_yards_sum_cum"] / (df["def_rush_att_cum"] + _eps)

    # ── Week 1 cold-start fill ────────────────────────────────────────────
    df = _fill_week1_cold_start(df)

    # ── Prior-season-blended features (new columns; old ones untouched) ───
    df = _add_blended_rate_features(df, blend_n)

    # ── Separate prior-season features (selectable, not blended) ──────────
    df = _add_prev_season_rate_features(df)
    df["games_played_this_season"] = df.groupby(["team", "season"]).cumcount()

    # ── Sample-size flags ─────────────────────────────────────────────────
    df["ol_pass_sample_size"]   = df["pass_att_cum"]
    df["ol_rush_sample_size"]   = df["rush_att_cum"]
    df["def_pass_sample_size"]  = df["def_pass_att_cum"]
    df["def_rush_sample_size"]  = df["def_rush_att_cum"]
    df["ol_pass_sufficient"]    = df["pass_att_cum"]    >= MIN_PLAY_SAMPLE
    df["ol_rush_sufficient"]    = df["rush_att_cum"]    >= MIN_PLAY_SAMPLE
    df["def_pass_sufficient"]   = df["def_pass_att_cum"] >= MIN_PLAY_SAMPLE
    df["def_rush_sufficient"]   = df["def_rush_att_cum"] >= MIN_PLAY_SAMPLE

    n_cold = (df["week"] == 1).sum()
    n_insuf = (~df["ol_pass_sufficient"]).sum()
    logger.info(
        f"  {n_cold:,} Week-1 rows filled with prior-season averages; "
        f"{n_insuf:,} rows flagged insufficient pass sample"
    )

    return df


def _full_season_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute each team's full-season rate averages by season.

    We use the cumulative RAW counts at each team's final game of the season,
    then ADD the current-week counts back in so the totals cover the full season.
    """
    last_week = df.groupby(["team", "season"])["week"].transform("max")
    season_final = df[df["week"] == last_week].copy()

    # At the final week, cum = through week N-2; add current week to get full season
    for raw, cum in [
        ("pass_att",          "pass_att_cum"),
        ("sacks",             "sacks_cum"),
        ("qb_hits",           "qb_hits_cum"),
        ("pass_epa_sum",      "pass_epa_sum_cum"),
        ("rush_att",          "rush_att_cum"),
        ("rush_epa_sum",      "rush_epa_sum_cum"),
        ("rush_yards_sum",    "rush_yards_sum_cum"),
        ("def_pass_att",      "def_pass_att_cum"),
        ("def_sacks",         "def_sacks_cum"),
        ("def_qb_hits",       "def_qb_hits_cum"),
        ("def_pass_epa_sum",  "def_pass_epa_sum_cum"),
        ("def_rush_att",      "def_rush_att_cum"),
        ("def_rush_epa_sum",  "def_rush_epa_sum_cum"),
        ("def_rush_yards_sum","def_rush_yards_sum_cum"),
    ]:
        season_final[f"{raw}_total"] = season_final[cum] + season_final[raw]

    _eps = 1e-9
    avgs = season_final[["team", "season"]].copy()
    avgs["ol_sack_rate"]                     = season_final["sacks_total"]         / (season_final["pass_att_total"]     + _eps)
    avgs["ol_qb_hit_rate"]                   = season_final["qb_hits_total"]       / (season_final["pass_att_total"]     + _eps)
    avgs["ol_pressure_proxy_rate"]           = (season_final["sacks_total"] + season_final["qb_hits_total"]) / (season_final["pass_att_total"] + _eps)
    avgs["ol_pass_epa_per_att"]              = season_final["pass_epa_sum_total"]  / (season_final["pass_att_total"]     + _eps)
    avgs["ol_rush_epa_per_att"]              = season_final["rush_epa_sum_total"]  / (season_final["rush_att_total"]     + _eps)
    avgs["ol_rush_yards_per_att"]            = season_final["rush_yards_sum_total"] / (season_final["rush_att_total"]    + _eps)
    avgs["def_sack_rate"]                    = season_final["def_sacks_total"]      / (season_final["def_pass_att_total"] + _eps)
    avgs["def_qb_hit_rate"]                  = season_final["def_qb_hits_total"]    / (season_final["def_pass_att_total"] + _eps)
    avgs["def_pressure_proxy_rate"]          = (season_final["def_sacks_total"] + season_final["def_qb_hits_total"]) / (season_final["def_pass_att_total"] + _eps)
    avgs["def_pass_epa_allowed_per_att"]     = season_final["def_pass_epa_sum_total"] / (season_final["def_pass_att_total"] + _eps)
    avgs["def_rush_epa_allowed_per_att"]     = season_final["def_rush_epa_sum_total"] / (season_final["def_rush_att_total"] + _eps)
    avgs["def_rush_yards_allowed_per_att"]   = season_final["def_rush_yards_sum_total"] / (season_final["def_rush_att_total"] + _eps)

    season_final["sacks_plus_qb_hits_total"] = (
        season_final["sacks_total"] + season_final["qb_hits_total"]
    )
    season_final["def_sacks_plus_qb_hits_total"] = (
        season_final["def_sacks_total"] + season_final["def_qb_hits_total"]
    )

    # Raw totals, exposed so blended (prior-N-games) features can scale them
    # without recomputing per-game aggregates from scratch. Additive only —
    # nothing above this line is touched.
    for col in [
        "pass_att_total", "sacks_total", "qb_hits_total", "pass_epa_sum_total",
        "rush_att_total", "rush_epa_sum_total", "rush_yards_sum_total",
        "def_pass_att_total", "def_sacks_total", "def_qb_hits_total",
        "def_pass_epa_sum_total", "def_rush_att_total", "def_rush_epa_sum_total",
        "def_rush_yards_sum_total",
        "sacks_plus_qb_hits_total", "def_sacks_plus_qb_hits_total",
    ]:
        avgs[col] = season_final[col].values

    games_played = df.groupby(["team", "season"])["week"].nunique()
    avgs["games_played"] = avgs.set_index(["team", "season"]).index.map(games_played).values

    return avgs.reset_index(drop=True)


def _fill_week1_cold_start(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace Week-1 rate features with prior-season full-season averages.

    For teams with no prior-season data (e.g. 2015 Week 1), substitute the
    league-wide average across all teams for the earliest available season.
    """
    # Compute full-season averages per (team, season)
    season_avgs = _full_season_averages(df)

    # Create lookup keyed by (team, season+1) so we can look up prior season
    prior_lookup = season_avgs.copy()
    prior_lookup["season"] = prior_lookup["season"] + 1   # map: prior_season → this_season
    prior_lookup = prior_lookup.set_index(["team", "season"])

    # Fall-back: league average of earliest season in avgs
    earliest = season_avgs["season"].min()
    league_avg = (
        season_avgs[season_avgs["season"] == earliest]
        [ALL_TEAM_RATE_FEATURES]
        .mean()
    )

    # Identify Week-1 rows that need filling
    week1_mask = df["week"] == 1
    logger.info(f"  Filling {week1_mask.sum():,} Week-1 rows …")

    df = df.copy()
    for feat in ALL_TEAM_RATE_FEATURES:
        filled = []
        for _, row in df[week1_mask][["team", "season"]].iterrows():
            key = (row["team"], row["season"])
            if key in prior_lookup.index:
                filled.append(prior_lookup.loc[key, feat])
            else:
                filled.append(league_avg[feat])
        df.loc[week1_mask, feat] = filled

    return df


# ── Prior-season blend (new columns; see PROMPT-PRIOR-SEASON-BLEND.md §3a) ───
#
# feature -> (numerator_total_col, denominator_total_col) in _full_season_averages' output
_RATE_BLEND_DEFS: dict[str, tuple[str, str]] = {
    "ol_sack_rate":                    ("sacks_total", "pass_att_total"),
    "ol_qb_hit_rate":                  ("qb_hits_total", "pass_att_total"),
    "ol_pressure_proxy_rate":          ("sacks_plus_qb_hits_total", "pass_att_total"),
    "ol_pass_epa_per_att":             ("pass_epa_sum_total", "pass_att_total"),
    "ol_rush_epa_per_att":             ("rush_epa_sum_total", "rush_att_total"),
    "ol_rush_yards_per_att":           ("rush_yards_sum_total", "rush_att_total"),
    "def_sack_rate":                   ("def_sacks_total", "def_pass_att_total"),
    "def_qb_hit_rate":                 ("def_qb_hits_total", "def_pass_att_total"),
    "def_pressure_proxy_rate":         ("def_sacks_plus_qb_hits_total", "def_pass_att_total"),
    "def_pass_epa_allowed_per_att":    ("def_pass_epa_sum_total", "def_pass_att_total"),
    "def_rush_epa_allowed_per_att":    ("def_rush_epa_sum_total", "def_rush_att_total"),
    "def_rush_yards_allowed_per_att":  ("def_rush_yards_sum_total", "def_rush_att_total"),
}

# feature -> cumulative (pre-week) numerator column(s); two features sum a pair.
_RATE_CUM_NUMERATOR: dict[str, list[str]] = {
    "ol_sack_rate":                    ["sacks_cum"],
    "ol_qb_hit_rate":                  ["qb_hits_cum"],
    "ol_pressure_proxy_rate":          ["sacks_cum", "qb_hits_cum"],
    "ol_pass_epa_per_att":             ["pass_epa_sum_cum"],
    "ol_rush_epa_per_att":             ["rush_epa_sum_cum"],
    "ol_rush_yards_per_att":           ["rush_yards_sum_cum"],
    "def_sack_rate":                   ["def_sacks_cum"],
    "def_qb_hit_rate":                 ["def_qb_hits_cum"],
    "def_pressure_proxy_rate":         ["def_sacks_cum", "def_qb_hits_cum"],
    "def_pass_epa_allowed_per_att":    ["def_pass_epa_sum_cum"],
    "def_rush_epa_allowed_per_att":    ["def_rush_epa_sum_cum"],
    "def_rush_yards_allowed_per_att":  ["def_rush_yards_sum_cum"],
}
_RATE_CUM_DENOMINATOR: dict[str, str] = {
    "ol_sack_rate":                    "pass_att_cum",
    "ol_qb_hit_rate":                  "pass_att_cum",
    "ol_pressure_proxy_rate":          "pass_att_cum",
    "ol_pass_epa_per_att":             "pass_att_cum",
    "ol_rush_epa_per_att":             "rush_att_cum",
    "ol_rush_yards_per_att":           "rush_att_cum",
    "def_sack_rate":                   "def_pass_att_cum",
    "def_qb_hit_rate":                 "def_pass_att_cum",
    "def_pressure_proxy_rate":         "def_pass_att_cum",
    "def_pass_epa_allowed_per_att":    "def_pass_att_cum",
    "def_rush_epa_allowed_per_att":    "def_rush_att_cum",
    "def_rush_yards_allowed_per_att":  "def_rush_att_cum",
}

ALL_TEAM_RATE_FEATURES_BLEND = [f"{f}_blend" for f in ALL_TEAM_RATE_FEATURES]
ALL_TEAM_RATE_FEATURES_PREV  = [f"{f}_prev"  for f in ALL_TEAM_RATE_FEATURES]


def _add_blended_rate_features(df: pd.DataFrame, N: int) -> pd.DataFrame:
    """
    Add `<feature>_blend` columns: the prior season enters as `N` pseudo-games,
    scaled from its full-season totals, fading as the current season's own
    cumulative totals accumulate.

        prior_scaled = prior_season_total * N / prior_season_games
        blend(W) = (cum_through_Wminus1 + prior_scaled_num)
                 / (cum_through_Wminus1 + prior_scaled_den)

    At week 1, cum_through_Wminus1 is 0 for every team, so blend reduces to
    the prior season's full-season rate — the same value _fill_week1_cold_start
    substitutes today (both divide the same total_num by the same total_den;
    the two differ only by the +1e-9 epsilon, which is negligible at realistic
    sample sizes).

    A team with no prior season (2015, or any (team, season) missing a prior
    row) falls back to the league-wide average rate for the earliest season,
    combined with that league's average per-game sample size — so the
    fallback prior still carries a realistic weight in the blend rather than
    a token one.

    Adds columns only; does not modify any existing column.
    """
    df = df.copy()
    season_totals = _full_season_averages(df)

    total_cols = [c for c in season_totals.columns if c.endswith("_total")]

    prior_lookup = season_totals.copy()
    prior_lookup["season"] = prior_lookup["season"] + 1
    prior_lookup = prior_lookup.rename(columns={c: f"prior_{c}" for c in total_cols})
    prior_lookup = prior_lookup.rename(columns={"games_played": "prior_games_played"})
    prior_lookup = prior_lookup[["team", "season", "prior_games_played"] + [f"prior_{c}" for c in total_cols]]

    earliest = season_totals["season"].min()
    early = season_totals[season_totals["season"] == earliest]
    league_avg_rate = early[ALL_TEAM_RATE_FEATURES].mean()
    league_den_pg = (early[total_cols].div(early["games_played"], axis=0)).mean()

    df = df.merge(prior_lookup, on=["team", "season"], how="left")
    has_prior = df["prior_games_played"].notna() & (df["prior_games_played"] > 0)

    for feat, (num_col, den_col) in _RATE_BLEND_DEFS.items():
        prior_games = df["prior_games_played"]
        prior_den_pg = np.where(
            has_prior, df[f"prior_{den_col}"] / prior_games, league_den_pg[den_col]
        )
        prior_num_pg = np.where(
            has_prior,
            df[f"prior_{num_col}"] / prior_games,
            league_avg_rate[feat] * league_den_pg[den_col],
        )

        cum_num = df[_RATE_CUM_NUMERATOR[feat][0]].copy()
        for extra in _RATE_CUM_NUMERATOR[feat][1:]:
            cum_num = cum_num + df[extra]
        cum_den = df[_RATE_CUM_DENOMINATOR[feat]]

        blended_num = cum_num + N * prior_num_pg
        blended_den = cum_den + N * prior_den_pg
        df[f"{feat}_blend"] = blended_num / (blended_den + 1e-9)

    return df.drop(columns=["prior_games_played"] + [f"prior_{c}" for c in total_cols])


def _add_prev_season_rate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add `<feature>_prev` columns: the prior season's full-season value,
    unblended, carried on every week of season S (not just week 1). These are
    selectable-but-not-live experiment features (see PROMPT §3b) — they close
    the capability gap where the catalog could not express a lagged
    prior-season aggregate (2026-09-09 hypothesis run).

    A team with no prior season falls back to the league-wide average of the
    earliest available season — the same fallback the week-1 cold start uses.
    """
    df = df.copy()
    season_avgs = _full_season_averages(df)

    prior_lookup = season_avgs.copy()
    prior_lookup["season"] = prior_lookup["season"] + 1

    earliest = season_avgs["season"].min()
    league_avg = season_avgs[season_avgs["season"] == earliest][ALL_TEAM_RATE_FEATURES].mean()

    merged = df[["team", "season"]].merge(
        prior_lookup[["team", "season"] + ALL_TEAM_RATE_FEATURES],
        on=["team", "season"], how="left",
    )
    for feat in ALL_TEAM_RATE_FEATURES:
        df[f"{feat}_prev"] = merged[feat].fillna(league_avg[feat]).values
    return df


# ── Game feature matrix ──────────────────────────────────────────────────────

def build_game_feature_matrix(
    games: pd.DataFrame,
    team_features: pd.DataFrame,
    team_feature_cols: list | None = None,
) -> pd.DataFrame:
    """
    Join team-level season-to-date features onto each game row.

    Each game gets:
      home_{feature}  — home team's features
      away_{feature}  — away team's features
      home_advantage  — always 1 (constant; captures stadium effect)
      div_game        — from curated.games
      roof_dome       — 1 if dome or retractable (closed), else 0
      temp            — game-time temperature; 70 default for dome games
      wind            — wind speed (mph); 0 default for dome games

    Parameters
    ----------
    team_feature_cols : optional list of feature column names to pull from
                        team_features.  Defaults to ALL_TEAM_RATE_FEATURES for
                        backward compatibility with v1.  Pass a larger list for
                        v2 (includes comprehensive + situational features).
    """
    feat_cols = team_feature_cols if team_feature_cols is not None else ALL_TEAM_RATE_FEATURES
    # Only select columns that actually exist in team_features
    available = [c for c in feat_cols if c in team_features.columns]
    missing   = [c for c in feat_cols if c not in team_features.columns]
    if missing:
        logger.warning(f"  build_game_feature_matrix: {len(missing)} feature cols not found in team_features and will be skipped: {missing[:10]}{'...' if len(missing) > 10 else ''}")

    tf = team_features[["team", "season", "week"] + available].copy()

    # Home team features
    home_tf = tf.rename(columns={"team": "home_team"})
    home_tf = home_tf.rename(columns={f: f"home_{f}" for f in available})

    # Away team features
    away_tf = tf.rename(columns={"team": "away_team"})
    away_tf = away_tf.rename(columns={f: f"away_{f}" for f in available})

    gf = games.copy()
    gf = gf.merge(home_tf, on=["home_team", "season", "week"], how="left")
    gf = gf.merge(away_tf, on=["away_team", "season", "week"], how="left")

    # Game-level context features
    gf["home_advantage"] = 1

    gf["div_game"] = gf["div_game"].fillna(False).astype(int)

    # roof_dome: 1 if dome or retractable (assumed closed)
    gf["roof_dome"] = gf["roof"].isin(["dome", "retractable"]).astype(int)

    # temp / wind: use 70 / 0 defaults for dome games
    gf["temp"] = gf["temp"].where(gf["roof_dome"] == 0, 70.0)
    gf["temp"] = gf["temp"].fillna(gf["temp"].median())  # outdoor nulls → median

    gf["wind"] = gf["wind"].where(gf["roof_dome"] == 0, 0.0)
    gf["wind"] = gf["wind"].fillna(0.0)

    # Verify join coverage
    home_feat_cols = [f"home_{f}" for f in available]
    away_feat_cols = [f"away_{f}" for f in available]
    missing_home = gf[home_feat_cols].isna().any(axis=1).sum()
    missing_away = gf[away_feat_cols].isna().any(axis=1).sum()
    if missing_home > 0 or missing_away > 0:
        logger.warning(
            f"  Feature join gaps: {missing_home} home rows, {missing_away} away rows "
            f"have at least one null feature. These will be imputed during training."
        )

    total = len(gf)
    with_target = gf["home_covered"].notna().sum()
    pushes = gf["home_covered"].isna().sum()
    logger.info(
        f"  Game matrix: {total:,} total games | "
        f"{with_target:,} with target | {pushes:,} pushes (null home_covered)"
    )
    return gf

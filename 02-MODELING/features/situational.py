"""
Situational / form features derived from curated.games.

These capture scheduling, momentum, and season-record context — none of which
can be derived from play-by-play data alone.

Features (per team, season-to-date through week W-1):
    rest_days           — calendar days since prior game (14 if first game or post-bye)
    prior_week_margin   — point differential in most recent completed game
                          (positive = won; 0 for Week 1 cold-start)
    season_win_pct      — cumulative W/(W+L) through prior week
                          (0.5 neutral prior at Week 1)

Derived game-level feature (NOT in the per-team output):
    rest_differential   — home_rest_days − away_rest_days
                          added in build_game_feature_matrix after joining

Week-1 cold-start defaults:
    rest_days         → 14 (full off-season rest assumed)
    prior_week_margin → 0  (no prior game this season)
    season_win_pct    → 0.5 (neutral prior)

Requires curated.games to include: game_id, season, week, game_date,
home_team, away_team, home_score, away_score
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Feature name constants ─────────────────────────────────────────────────────

SITUATIONAL_TEAM_FEATURES = [
    "rest_days",
    "prior_week_margin",
    "season_win_pct",
]

# rest_differential is game-level; listed here for documentation
SITUATIONAL_GAME_FEATURES = [
    "rest_differential",
]


# ── Main computation ───────────────────────────────────────────────────────────

def compute_situational_features(games: pd.DataFrame) -> pd.DataFrame:
    """
    Compute situational/form features per (team, season, week).

    Returns a DataFrame with columns:
        team, season, week, rest_days, prior_week_margin, season_win_pct

    All values reflect data available BEFORE the game in that (season, week)
    — i.e., they are safe to use as features without look-ahead leakage.

    Parameters
    ----------
    games : curated.games DataFrame.
            Must include: game_id, season, week, game_date,
                          home_team, away_team, home_score, away_score
    """
    logger.info("Computing situational/form features ...")

    # ── 1. Build team-perspective game log ────────────────────────────────
    # Each game yields two rows: one for home team, one for away team.
    games = games.copy()
    games["game_date"] = pd.to_datetime(games["game_date"])

    home_rows = games[[
        "game_id", "season", "week", "game_date",
        "home_team", "away_team", "home_score", "away_score",
    ]].copy()
    home_rows["team"]   = home_rows["home_team"]
    home_rows["margin"] = home_rows["home_score"] - home_rows["away_score"]
    home_rows["win"]    = (home_rows["margin"] > 0).astype(float)
    home_rows["loss"]   = (home_rows["margin"] < 0).astype(float)

    away_rows = games[[
        "game_id", "season", "week", "game_date",
        "home_team", "away_team", "home_score", "away_score",
    ]].copy()
    away_rows["team"]   = away_rows["away_team"]
    away_rows["margin"] = away_rows["away_score"] - away_rows["home_score"]
    away_rows["win"]    = (away_rows["margin"] > 0).astype(float)
    away_rows["loss"]   = (away_rows["margin"] < 0).astype(float)

    team_games = (
        pd.concat([home_rows, away_rows], ignore_index=True)
        [["team", "season", "week", "game_date", "margin", "win", "loss"]]
        .sort_values(["team", "season", "week"])
        .reset_index(drop=True)
    )

    # Handle missing scores — treat as push (margin=0, win=0, loss=0)
    team_games["margin"] = team_games["margin"].fillna(0.0)
    team_games["win"]    = team_games["win"].fillna(0.0)
    team_games["loss"]   = team_games["loss"].fillna(0.0)

    # ── 2. rest_days ──────────────────────────────────────────────────────
    # Days between consecutive games FOR THE SAME TEAM in the same season.
    # Cross-season gaps are replaced with 14 (season opener / bye-equivalent).
    team_games["prev_date"] = (
        team_games.groupby(["team", "season"])["game_date"].shift(1)
    )
    team_games["rest_days_raw"] = (
        (team_games["game_date"] - team_games["prev_date"]).dt.days
    )
    # Week 1 within a season (no prior game): default to 14
    team_games["rest_days_raw"] = team_games["rest_days_raw"].fillna(14.0)
    # Sanity clamp: [3, 21] — anything outside this range is a data issue
    team_games["rest_days_raw"] = team_games["rest_days_raw"].clip(lower=3, upper=21)

    # ── 3. prior_week_margin ──────────────────────────────────────────────
    # Margin from the immediately prior game (season-scoped; Week 1 = 0)
    team_games["prior_week_margin_raw"] = (
        team_games.groupby(["team", "season"])["margin"].shift(1)
    )
    team_games["prior_week_margin_raw"] = team_games["prior_week_margin_raw"].fillna(0.0)

    # ── 4. season_win_pct ─────────────────────────────────────────────────
    # Cumulative W/(W+L) through week W-1.
    # Uses cumsum shifted by 1 to exclude the current game.
    team_games["cum_wins_through_prior"] = (
        team_games.groupby(["team", "season"])["win"].cumsum()
        - team_games["win"]
    )
    team_games["cum_losses_through_prior"] = (
        team_games.groupby(["team", "season"])["loss"].cumsum()
        - team_games["loss"]
    )
    denom = team_games["cum_wins_through_prior"] + team_games["cum_losses_through_prior"]
    team_games["season_win_pct_raw"] = np.where(
        denom > 0,
        team_games["cum_wins_through_prior"] / denom,
        0.5,  # neutral prior when no prior games
    )

    # ── 5. Rename to final feature names ──────────────────────────────────
    result = team_games[[
        "team", "season", "week",
        "rest_days_raw", "prior_week_margin_raw", "season_win_pct_raw",
    ]].copy()
    result = result.rename(columns={
        "rest_days_raw":          "rest_days",
        "prior_week_margin_raw":  "prior_week_margin",
        "season_win_pct_raw":     "season_win_pct",
    })

    logger.info(
        f"  Situational features built for {result['team'].nunique()} teams, "
        f"{result['season'].nunique()} seasons"
    )
    return result


def add_rest_differential(game_features: pd.DataFrame) -> pd.DataFrame:
    """
    Derive rest_differential = home_rest_days - away_rest_days at game level.

    Call this AFTER build_game_feature_matrix has joined situational features,
    so home_rest_days and away_rest_days are present.

    Returns game_features with rest_differential column added.
    """
    if "home_rest_days" not in game_features.columns:
        raise ValueError(
            "home_rest_days not found — call after joining situational features"
        )
    gf = game_features.copy()
    gf["rest_differential"] = gf["home_rest_days"] - gf["away_rest_days"]
    return gf

"""
OL mismatch flag computation.

Approved definition (PROJECT-LEAD, 2026-05-03)
-----------------------------------------------

Offensive composite (higher = better OL offense):
    ol_composite = Z(ol_pass_epa_per_att) − Z(ol_pressure_proxy_rate)

Defensive composite (higher = better defense):
    def_composite = Z(def_pressure_proxy_rate) − Z(def_pass_epa_allowed_per_att)

    NOTE: The defensive composite was revised from the initial proposal.
    The original Z(def_pass_epa_allowed_per_att) − Z(def_pressure_proxy_rate)
    was directionally inconsistent: a high value meant a BAD defense, so
    "bottom quartile" would have selected good defenses.  The approved formula
    inverts this so that higher = better defense throughout.

Z-score reference distribution
-------------------------------
For a game at (season=S, week=W), Z-scores are computed using the combined
home + away distribution of all games in season S through week W (inclusive).
Using a combined pool (not separate home/away distributions) ensures that the
same standardized scale is applied to both home and away teams in a game.

Quartile boundaries
-------------------
Per-season, expanding through week W.  The 75th-percentile cutoff for
top-quartile offense and the 25th-percentile cutoff for bottom-quartile defense
are both derived from the same expanding within-season pool.

Flag values
-----------
  1  — home team top-quartile OL offense AND away team bottom-quartile defense
  2  — away team top-quartile OL offense AND home team bottom-quartile defense
  0  — neither condition met
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Offensive component features
OFF_EPA    = "ol_pass_epa_per_att"        # higher = better
OFF_PRESS  = "ol_pressure_proxy_rate"     # lower = better (enters negatively)

# Defensive component features (approved corrected formula)
DEF_PRESS  = "def_pressure_proxy_rate"    # higher = better defense (enters positively)
DEF_EPA    = "def_pass_epa_allowed_per_att"  # lower = better (enters negatively)


# ── Z-score helpers ───────────────────────────────────────────────────────────

def _expanding_zscores(
    game_features: pd.DataFrame,
    home_col: str,
    away_col: str,
) -> tuple[pd.Series, pd.Series]:
    """
    For each game, Z-score both home and away values of a feature using the
    combined distribution of all games in the same season through the same week.

    The reference distribution at (season=S, week=W) is:
      {home_col for all games in S, weeks ≤ W} ∪ {away_col for all games in S, weeks ≤ W}

    Returns (home_zscores, away_zscores) indexed like game_features.
    """
    home_z = pd.Series(np.nan, index=game_features.index, dtype=float)
    away_z = pd.Series(np.nan, index=game_features.index, dtype=float)

    for season in sorted(game_features["season"].unique()):
        s_mask = game_features["season"] == season
        s_games = game_features[s_mask]

        for week in sorted(s_games["week"].unique()):
            # Reference: all home + away values in this season through this week
            ref_mask = s_mask & (game_features["week"] <= week)
            ref_vals = pd.concat([
                game_features.loc[ref_mask, home_col],
                game_features.loc[ref_mask, away_col],
            ]).dropna()

            mu    = ref_vals.mean()
            sigma = ref_vals.std(ddof=1)

            w_mask = s_mask & (game_features["week"] == week)
            if sigma > 1e-9:
                home_z[w_mask] = (game_features.loc[w_mask, home_col] - mu) / sigma
                away_z[w_mask] = (game_features.loc[w_mask, away_col] - mu) / sigma
            else:
                # All teams identical this week; Z = 0 by convention
                home_z[w_mask] = 0.0
                away_z[w_mask] = 0.0

    return home_z, away_z


# ── Composite computation ─────────────────────────────────────────────────────

def compute_ol_mismatch_flag(game_features: pd.DataFrame) -> pd.DataFrame:
    """
    Add `ol_mismatch_flag` to the game feature matrix.

    Inputs required in game_features:
      home_ol_pass_epa_per_att, home_ol_pressure_proxy_rate
      away_ol_pass_epa_per_att, away_ol_pressure_proxy_rate
      home_def_pressure_proxy_rate, home_def_pass_epa_allowed_per_att
      away_def_pressure_proxy_rate, away_def_pass_epa_allowed_per_att
      season, week

    Outputs added to game_features:
      home_ol_composite       — offensive composite, home team
      away_ol_composite       — offensive composite, away team
      home_def_composite      — defensive composite, home team
      away_def_composite      — defensive composite, away team
      ol_mismatch_flag        — 0, 1, or 2
    """
    logger.info("Computing OL mismatch composites …")
    gf = game_features.copy()

    # ── Offensive composite components ────────────────────────────────────────
    logger.info("  Z-scoring offensive composite components …")
    home_epa_z, away_epa_z   = _expanding_zscores(gf, f"home_{OFF_EPA}",   f"away_{OFF_EPA}")
    home_pres_z, away_pres_z = _expanding_zscores(gf, f"home_{OFF_PRESS}", f"away_{OFF_PRESS}")

    # ol_composite = Z(pass_epa) − Z(pressure_rate)  [higher = better offense]
    gf["home_ol_composite"] = home_epa_z - home_pres_z
    gf["away_ol_composite"] = away_epa_z - away_pres_z

    # ── Defensive composite components (corrected formula) ────────────────────
    # def_composite = Z(def_pressure_proxy_rate) − Z(def_pass_epa_allowed)
    # Higher = better defense.  Bottom quartile = weakest defenses.
    logger.info("  Z-scoring defensive composite components …")
    home_dp_z, away_dp_z  = _expanding_zscores(gf, f"home_{DEF_PRESS}", f"away_{DEF_PRESS}")
    home_de_z, away_de_z  = _expanding_zscores(gf, f"home_{DEF_EPA}",   f"away_{DEF_EPA}")

    gf["home_def_composite"] = home_dp_z - home_de_z
    gf["away_def_composite"] = away_dp_z - away_de_z

    # ── Quartile boundaries (per-season, expanding through each week) ─────────
    logger.info("  Computing per-season per-week quartile thresholds …")
    flags = pd.Series(0, index=gf.index, dtype=int)

    for season in sorted(gf["season"].unique()):
        s_mask = gf["season"] == season
        s_games = gf[s_mask]

        for week in sorted(s_games["week"].unique()):
            ref_mask = s_mask & (gf["week"] <= week)
            w_mask   = s_mask & (gf["week"] == week)

            # Offensive quartile: combined home + away composite
            off_ref = pd.concat([
                gf.loc[ref_mask, "home_ol_composite"],
                gf.loc[ref_mask, "away_ol_composite"],
            ]).dropna()

            # Defensive quartile: combined home + away composite
            def_ref = pd.concat([
                gf.loc[ref_mask, "home_def_composite"],
                gf.loc[ref_mask, "away_def_composite"],
            ]).dropna()

            if len(off_ref) < 4 or len(def_ref) < 4:
                # Not enough data to set quartiles (very early season); skip
                continue

            off_p75 = off_ref.quantile(0.75)  # top-quartile offense threshold
            def_p25 = def_ref.quantile(0.25)  # bottom-quartile defense threshold

            # flag = 1: home elite OL offense AND away weak defense
            home_elite_off = gf.loc[w_mask, "home_ol_composite"] >= off_p75
            away_weak_def  = gf.loc[w_mask, "away_def_composite"] <= def_p25
            flag1_mask = w_mask & home_elite_off & away_weak_def

            # flag = 2: away elite OL offense AND home weak defense
            away_elite_off = gf.loc[w_mask, "away_ol_composite"] >= off_p75
            home_weak_def  = gf.loc[w_mask, "home_def_composite"] <= def_p25
            flag2_mask = w_mask & away_elite_off & home_weak_def

            # flag=1 takes priority; games can't be both (different teams' OLs)
            flags[flag1_mask] = 1
            flags[flag2_mask & ~flag1_mask] = 2

    gf["ol_mismatch_flag"] = flags

    # Summary
    n_flag1 = (gf["ol_mismatch_flag"] == 1).sum()
    n_flag2 = (gf["ol_mismatch_flag"] == 2).sum()
    n_total = len(gf)
    logger.info(
        f"  Mismatch flags: {n_flag1} flag=1 ({n_flag1/n_total:.1%}) | "
        f"{n_flag2} flag=2 ({n_flag2/n_total:.1%}) | "
        f"{n_total - n_flag1 - n_flag2} flag=0"
    )

    return gf


# ── Subset ATS metrics ────────────────────────────────────────────────────────

def subset_ats_record(predictions: pd.DataFrame, flag_value: int = 1) -> dict:
    """
    Compute ATS record for the OL mismatch subset.

    predictions must have: ol_mismatch_flag, correct, actual_home_covered
    """
    sub = predictions[predictions["ol_mismatch_flag"] == flag_value].copy()
    decided = sub.dropna(subset=["correct"])
    wins   = int(decided["correct"].sum())
    losses = int(len(decided) - wins)
    pushes = int(sub["actual_home_covered"].isna().sum())
    n      = wins + losses
    return {
        "flag_value":  flag_value,
        "n_games":     n,
        "wins":        wins,
        "losses":      losses,
        "pushes":      pushes,
        "hit_rate":    wins / n if n > 0 else float("nan"),
    }

"""
Per-game pick explanations — enrichment layer on top of
OLXGBModel.explain() (STAGE 1.1/1.2 of PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md).

model.explain() gives exact TreeSHAP contributions per (row, feature). This
module adds everything that needs game/team context the model itself doesn't
have: which game a row belongs to, home/away/game side, feature family,
league percentile, the pick-direction re-signing, and the family matchup view.

No BigQuery import here — this is pure pandas so it can be unit tested with
synthetic frames. Storage lives in explanations_bq.py.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from features.families import base_feature_name, feature_family, feature_side


def feature_list_hash(feature_list: list[str]) -> str:
    """Stable short hash identifying exactly which features a model was trained on."""
    canonical = json.dumps(list(feature_list), sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _percentile_table(team_features: pd.DataFrame, base_features: list[str]) -> pd.DataFrame:
    """
    team, season, week + one `<feat>_pctile` column per base feature: this
    team's percentile rank of that feature's raw value among all teams with a
    row for the same (season, week).
    """
    out = team_features[["team", "season", "week"]].copy()
    for f in base_features:
        if f in team_features.columns:
            out[f"{f}_pctile"] = (
                team_features.groupby(["season", "week"])[f].rank(pct=True) * 100.0
            )
    return out


def build_explanations(
    model,
    X_raw: pd.DataFrame,
    games_meta: pd.DataFrame,
    predicted_side: pd.Series,
    predicted_home_cover_prob: pd.Series,
    team_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the long-format explanation table for a batch of games.

    Parameters
    ----------
    model                        : a fitted OLXGBModel (or subclass)
    X_raw                        : model input matrix, index aligned with games_meta
    games_meta                   : DataFrame (same index as X_raw) with at least
                                    game_id, season, week, home_team, away_team
    predicted_side               : Series (same index) of 'home'/'away'
    predicted_home_cover_prob    : Series (same index) of P(home cover)
    team_features                : optional long (team, season, week, <base features>)
                                    table for league_pctile. Omitted -> league_pctile
                                    is NaN for every row (still valid, just less rich).

    Returns
    -------
    Long DataFrame, one row per (game, feature):
        game_id, season, week, home_team, away_team, feature, side, family,
        raw_value, league_pctile, was_imputed, contribution_logodds,
        pick_direction_contribution, abs_rank, bias_logodds, row_sum_logodds,
        predicted_side, predicted_home_cover_prob
    """
    exp = model.explain(X_raw)  # row, feature, raw_value, was_imputed, contribution_logodds, bias_logodds, row_sum_logodds, abs_rank

    meta_cols = ["game_id", "season", "week", "home_team", "away_team"]
    exp = exp.merge(
        games_meta[meta_cols], left_on="row", right_index=True, how="left",
    )

    exp["side"] = exp["feature"].map(feature_side)
    exp["family"] = exp["feature"].map(feature_family)
    exp["base_feature"] = exp["feature"].map(base_feature_name)

    exp["predicted_side"] = exp["row"].map(predicted_side)
    exp["predicted_home_cover_prob"] = exp["row"].map(predicted_home_cover_prob)

    # Pick-direction view: re-sign so positive always means "toward the side
    # the model picked" (STAGE 1.2 §2, pick-direction view).
    exp["pick_direction_contribution"] = np.where(
        exp["predicted_side"] == "home",
        exp["contribution_logodds"],
        -exp["contribution_logodds"],
    )

    # League percentile: only meaningful for home/away (team-level) features.
    if team_features is not None:
        base_features = sorted(
            exp.loc[exp["side"] != "game", "base_feature"].unique().tolist()
        )
        pct_table = _percentile_table(team_features, base_features)
        pct_long = pct_table.melt(
            id_vars=["team", "season", "week"], var_name="feat_pctile", value_name="pctile_value"
        )
        pct_long["base_feature"] = pct_long["feat_pctile"].str.replace(r"_pctile$", "", regex=True)
        pct_long = pct_long.drop(columns=["feat_pctile"])

        exp["team_for_pctile"] = np.select(
            [exp["side"] == "home", exp["side"] == "away"],
            [exp["home_team"], exp["away_team"]],
            default=None,
        )
        merged = exp.merge(
            pct_long.rename(columns={"team": "team_for_pctile"}),
            on=["team_for_pctile", "season", "week", "base_feature"],
            how="left",
        )
        exp = exp.assign(league_pctile=merged["pctile_value"].to_numpy())
        exp = exp.drop(columns=["team_for_pctile"])
    else:
        exp["league_pctile"] = np.nan

    exp = exp.drop(columns=["base_feature"]).rename(columns={"row": "row_id"})
    return exp


def matchup_view(exp: pd.DataFrame) -> pd.DataFrame:
    """
    Per game, per family: home contribution, away contribution, and their
    net (sum — both are already signed toward P(home cover), so the sum is
    the family's total pull on that same target). Excludes game-level
    (side='game') features, which have no home/away split.
    """
    team_level = exp[exp["side"].isin(["home", "away"])]
    pivot = (
        team_level.groupby(["game_id", "family", "side"])["contribution_logodds"]
        .sum()
        .unstack("side")
        .reindex(columns=["home", "away"])
        .fillna(0.0)
    )
    pivot["net"] = pivot["home"] + pivot["away"]
    return pivot.reset_index().rename(
        columns={"home": "home_contribution", "away": "away_contribution"}
    )


def top_drivers(exp: pd.DataFrame, game_id: str, n: int = 5) -> pd.DataFrame:
    """Top-n features by |pick_direction_contribution| for one game."""
    g = exp[exp["game_id"] == game_id].copy()
    g["_abs"] = g["pick_direction_contribution"].abs()
    return g.sort_values("_abs", ascending=False).head(n).drop(columns=["_abs"])

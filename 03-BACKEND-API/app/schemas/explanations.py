"""
Schemas for GET /api/v1/predictions/{game_id}/explanation.

Backs the per-game "Why this pick" panel (PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md
STAGE 1.7). Source table: experiments.prediction_explanations, one row per
(game, feature) — see 02-MODELING/backtests/explanations_bq.py for the writer.
"""
from typing import Literal, Optional

from pydantic import BaseModel


class ExplanationFeature(BaseModel):
    """One feature's TreeSHAP contribution to a single game's prediction."""
    feature: str
    side: Literal["home", "away", "game"]
    family: str
    raw_value: Optional[float] = None
    league_pctile: Optional[float] = None
    was_imputed: bool
    contribution_logodds: float
    pick_direction_contribution: float
    abs_rank: int


class FamilyMatchup(BaseModel):
    """Per-family net contribution, home vs away — 'home OL pass protection vs away pass rush'."""
    family: str
    home_contribution: float
    away_contribution: float
    net: float


class GameExplanationResponse(BaseModel):
    """
    Full per-game explanation: top drivers, the family matchup view, and every
    feature the model saw.

    is_approximate / reproduction_max_diff are non-null only for picks
    backfilled by explain_picks.py where the reproduction guard did not match
    exactly (STAGE 1.6) — the UI must label these as approximate. clean_forward
    means only "not regenerated after this game kicked off"; it is unrelated
    to is_approximate.

    The live pick is authoritative (2026-09-17 decision, STATE.md): an
    approximate explanation can lean the other way from the pick the app
    actually made. `predicted_side` is this explanation's own model lean;
    `live_predicted_side` is the pick actually served by
    GET /api/v1/predictions; `side_matches_live_pick` is False exactly when
    they disagree. The UI must always name `live_predicted_side` in the
    heading, never `predicted_side`, and show a warning when they disagree.
    `top_drivers`/`all_features` carry `pick_direction_contribution` re-signed
    relative to `live_predicted_side`, not this run's own `predicted_side`.
    """
    game_id: str
    experiment_id: str
    run_id: str
    model_name: str
    predicted_side: Literal["home", "away"]
    live_predicted_side: Literal["home", "away"]
    side_matches_live_pick: bool
    predicted_home_cover_prob: float
    bias_logodds: float
    clean_forward: Optional[bool] = None
    is_approximate: bool
    reproduction_max_diff: Optional[float] = None
    top_drivers: list[ExplanationFeature]
    family_matchup: list[FamilyMatchup]
    all_features: list[ExplanationFeature]

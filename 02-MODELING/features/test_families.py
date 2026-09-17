"""
Coverage test for features/families.py — every feature the model can actually
be given must resolve to a family, or Stage 1's per-game explanations
silently drop coverage for it.

Run:
    cd 02-MODELING && python -m pytest features/test_families.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.families import FAMILIES, base_feature_name, feature_family, feature_side  # noqa: E402
from features.ol_metrics import (  # noqa: E402
    ALL_TEAM_RATE_FEATURES,
    ALL_TEAM_RATE_FEATURES_BLEND,
    ALL_TEAM_RATE_FEATURES_PREV,
    GAME_CONTEXT_FEATURES,
)
from features.comprehensive import (  # noqa: E402
    ALL_ADDITIONAL_TEAM_FEATURES,
    ALL_ADDITIONAL_TEAM_FEATURES_BLEND,
    ALL_ADDITIONAL_TEAM_FEATURES_PREV,
)
from features.situational import (  # noqa: E402
    SITUATIONAL_TEAM_FEATURES,
    SITUATIONAL_FEATURES_BLEND,
    SITUATIONAL_TEAM_FEATURES_PREV,
)

BASE_23 = ALL_TEAM_RATE_FEATURES + ALL_ADDITIONAL_TEAM_FEATURES + SITUATIONAL_TEAM_FEATURES

ALL_KNOWN_FEATURES = (
    BASE_23
    + ALL_TEAM_RATE_FEATURES_BLEND
    + ALL_TEAM_RATE_FEATURES_PREV
    + ALL_ADDITIONAL_TEAM_FEATURES_BLEND
    + ALL_ADDITIONAL_TEAM_FEATURES_PREV
    + SITUATIONAL_FEATURES_BLEND
    + SITUATIONAL_TEAM_FEATURES_PREV
    + GAME_CONTEXT_FEATURES
    + ["rest_differential", "games_played_this_season"]
)


def test_base_23_have_a_family():
    for f in BASE_23:
        assert feature_family(f) in FAMILIES, f


@pytest.mark.parametrize("feature", ALL_KNOWN_FEATURES)
def test_every_known_feature_has_a_family(feature):
    assert feature_family(feature) in FAMILIES


@pytest.mark.parametrize("feature", ALL_KNOWN_FEATURES)
def test_home_away_prefixed_variants_resolve_too(feature):
    assert feature_family(f"home_{feature}") == feature_family(feature)
    assert feature_family(f"away_{feature}") == feature_family(feature)


def test_unknown_feature_raises():
    with pytest.raises(KeyError):
        feature_family("totally_made_up_feature")


def test_feature_side():
    assert feature_side("home_ol_sack_rate") == "home"
    assert feature_side("away_ol_sack_rate") == "away"
    assert feature_side("temp") == "game"
    assert feature_side("rest_differential") == "game"


def test_avg_margin_blend_is_not_stripped_to_avg_margin():
    # avg_margin_blend is a direct entry (counterpart of prior_week_margin,
    # not "<base>_blend") — stripping the suffix would look up "avg_margin",
    # which has no family and must not silently succeed some other way.
    assert base_feature_name("avg_margin_blend") == "avg_margin_blend"
    assert feature_family("avg_margin_blend") == "record/margin"


def test_season_win_pct_blend_strips_correctly():
    # season_win_pct_blend DOES follow the "<base>_blend" pattern.
    assert base_feature_name("season_win_pct_blend") == "season_win_pct"
    assert feature_family("season_win_pct_blend") == "record/margin"

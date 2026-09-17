"""
Feature family map — the single classification used everywhere a feature's
contribution needs to be grouped into a human-readable bucket (per-game
explanations, the week analysis, the leave-one-family-out grids, the feature
family page).

One constant map, one place. Nothing computes its own family grouping.

Every feature in PRODUCTION_FEATURE_LIST (predict_upcoming.py), the base 23
curated features, their `_blend` / `_prev` counterparts, and the game-context
features must resolve through `feature_family()` — see
test_families.py::test_every_known_feature_has_a_family, which fails the
build the day a new feature is added to a builder without a family.
"""
from __future__ import annotations

FAMILIES = [
    "OL pass protection",
    "OL run blocking",
    "QB",
    "run game",
    "defence pass rush",
    "defence run",
    "coverage/defence other",
    "form",
    "record/margin",
    "rest",
    "weather",
    "venue/context",
]

# Base feature name (no home_/away_ prefix, no _blend/_prev suffix) -> family.
# Covers: ol_metrics.ALL_TEAM_RATE_FEATURES (12), comprehensive.ALL_ADDITIONAL_TEAM_FEATURES (8),
# situational.SITUATIONAL_TEAM_FEATURES (3) = the base 23, plus GAME_CONTEXT_FEATURES,
# rest_differential, games_played_this_season, and avg_margin_blend (which does not
# follow the "<base>_blend" naming pattern — its base is prior_week_margin).
_FAMILY_MAP: dict[str, str] = {
    # ── OL pass protection (rate of pressure allowed) ──────────────────────
    "ol_sack_rate": "OL pass protection",
    "ol_qb_hit_rate": "OL pass protection",
    "ol_pressure_proxy_rate": "OL pass protection",
    # ── OL run blocking ─────────────────────────────────────────────────────
    "ol_rush_epa_per_att": "OL run blocking",
    "ol_rush_yards_per_att": "OL run blocking",
    # ── QB / passing efficiency ─────────────────────────────────────────────
    "ol_pass_epa_per_att": "QB",
    "qb_cpoe": "QB",
    "qb_epa_under_pressure": "QB",
    "pass_explosive_rate": "QB",
    # ── Run game (explosiveness, as distinct from OL run blocking's epa/ypc) ─
    "rush_explosive_rate": "run game",
    # ── Defence pass rush (generated pressure) ──────────────────────────────
    "def_sack_rate": "defence pass rush",
    "def_qb_hit_rate": "defence pass rush",
    "def_pressure_proxy_rate": "defence pass rush",
    # ── Defence run ──────────────────────────────────────────────────────────
    "def_rush_epa_allowed_per_att": "defence run",
    "def_rush_yards_allowed_per_att": "defence run",
    "def_explosive_rush_allowed_rate": "defence run",
    # ── Coverage / defence other (pass efficiency allowed, broader than rush) ─
    "def_pass_epa_allowed_per_att": "coverage/defence other",
    "def_epa_per_play": "coverage/defence other",
    "def_explosive_pass_allowed_rate": "coverage/defence other",
    # ── Form ─────────────────────────────────────────────────────────────────
    "rolling_3wk_epa_trend": "form",
    # ── Record / margin ──────────────────────────────────────────────────────
    "prior_week_margin": "record/margin",
    "season_win_pct": "record/margin",
    "avg_margin_blend": "record/margin",  # counterpart of prior_week_margin, not "<base>_blend"
    "games_played_this_season": "record/margin",
    # ── Rest ─────────────────────────────────────────────────────────────────
    "rest_days": "rest",
    "rest_differential": "rest",
    # ── Weather ──────────────────────────────────────────────────────────────
    "roof_dome": "weather",
    "temp": "weather",
    "wind": "weather",
    # ── Venue / context ──────────────────────────────────────────────────────
    "home_advantage": "venue/context",
    "div_game": "venue/context",
}


def base_feature_name(feature: str) -> str:
    """Strip home_/away_ prefix and _blend/_prev suffix, in that order.

    A direct hit in _FAMILY_MAP always wins before any stripping: both
    "home_advantage" (a full feature name that happens to start with
    "home_") and "avg_margin_blend" (a direct entry that does not follow
    the "<base>_blend" pattern) must resolve without being torn apart.
    """
    if feature in _FAMILY_MAP:
        return feature
    name = feature
    for pfx in ("home_", "away_"):
        if name.startswith(pfx) and name != "home_advantage":
            name = name[len(pfx):]
            break
    if name in _FAMILY_MAP:
        return name
    for sfx in ("_blend", "_prev"):
        if name.endswith(sfx):
            stripped = name[: -len(sfx)]
            if stripped in _FAMILY_MAP:
                return stripped
    return name


def feature_side(feature: str) -> str:
    """'home' / 'away' / 'game' — from the home_/away_ prefix, or 'game' for context features."""
    if feature.startswith("home_"):
        return "home"
    if feature.startswith("away_"):
        return "away"
    return "game"


def feature_family(feature: str) -> str:
    """
    Resolve a (possibly home_/away_-prefixed, possibly _blend/_prev-suffixed)
    feature name to its family.

    Raises KeyError for anything not in _FAMILY_MAP — a new feature added to a
    builder without a family entry here is a build-time defect, not a silent
    "uncategorized" bucket.
    """
    base = base_feature_name(feature)
    try:
        return _FAMILY_MAP[base]
    except KeyError as exc:
        raise KeyError(
            f"No family mapped for feature {feature!r} (resolved base name "
            f"{base!r}). Add it to features/families.py::_FAMILY_MAP."
        ) from exc


def all_mapped_base_features() -> set[str]:
    return set(_FAMILY_MAP)

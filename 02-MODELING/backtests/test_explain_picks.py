"""
Unit tests for explain_picks.py's reproduction guard (STAGE 1.2 test:
"reproduction guard refuses on a 1e-3 perturbation"). No BigQuery network
calls: load_stored_predictions / generate_predictions are monkeypatched.

Run:
    cd 02-MODELING && python -m pytest backtests/test_explain_picks.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests import explain_picks as ep  # noqa: E402


def _stored(probs, sides, game_ids=("G1", "G2", "G3")):
    return pd.DataFrame({
        "game_id": list(game_ids),
        "home_team": ["H1", "H2", "H3"],
        "away_team": ["A1", "A2", "A3"],
        "predicted_home_cover_prob": list(probs),
        "predicted_side": list(sides),
    })


def _reproduced(probs, sides, game_ids=("G1", "G2", "G3")):
    return pd.DataFrame({
        "game_id": list(game_ids),
        "predicted_home_cover_prob": list(probs),
        "predicted_side": list(sides),
    })


def test_compare_predictions_no_diff_is_all_zero():
    stored = _stored([0.51, 0.49, 0.60], ["home", "away", "home"])
    reproduced = _reproduced([0.51, 0.49, 0.60], ["home", "away", "home"])
    diff = ep.compare_predictions(stored, reproduced)
    assert (diff["diff"] < 1e-12).all()
    assert not diff["side_flipped"].any()


def test_guard_refuses_on_a_1e_minus_3_perturbation(monkeypatch):
    stored = _stored([0.51, 0.49, 0.60], ["home", "away", "home"])
    # Perturb game G2 by 1e-3 — well above the 1e-6 tolerance.
    reproduced = _reproduced([0.51, 0.49 + 1e-3, 0.60], ["home", "away", "home"])

    monkeypatch.setattr(ep, "load_stored_predictions", lambda client, season, week: stored)
    monkeypatch.setattr(
        ep, "generate_predictions",
        lambda client, season, week, feature_list=None, blend_n=None: (reproduced, {"_model": None}),
    )

    passed, diff_table, repro, meta = ep.run_reproduction_guard(client=object(), season=2026, week=1, allow_non_linux=True)
    assert passed is False
    mismatched = diff_table[diff_table["diff"] > ep.REPRODUCTION_TOLERANCE]
    assert list(mismatched["game_id"]) == ["G2"]


def test_guard_passes_within_tolerance(monkeypatch):
    stored = _stored([0.51, 0.49, 0.60], ["home", "away", "home"])
    # Well under 1e-6.
    reproduced = _reproduced([0.51 + 1e-9, 0.49, 0.60 - 1e-9], ["home", "away", "home"])

    monkeypatch.setattr(ep, "load_stored_predictions", lambda client, season, week: stored)
    monkeypatch.setattr(
        ep, "generate_predictions",
        lambda client, season, week, feature_list=None, blend_n=None: (reproduced, {"_model": None}),
    )

    passed, diff_table, repro, meta = ep.run_reproduction_guard(client=object(), season=2026, week=1, allow_non_linux=True)
    assert passed is True


def test_guard_fails_on_a_side_flip_even_with_small_prob_diff(monkeypatch):
    # A side flip right at the 0.5 boundary can come with a tiny prob diff —
    # must still fail the guard, not just compare |diff| against tolerance.
    stored = _stored([0.501, 0.49, 0.60], ["home", "away", "home"])
    reproduced = _reproduced([0.499, 0.49, 0.60], ["away", "away", "home"])

    monkeypatch.setattr(ep, "load_stored_predictions", lambda client, season, week: stored)
    monkeypatch.setattr(
        ep, "generate_predictions",
        lambda client, season, week, feature_list=None, blend_n=None: (reproduced, {"_model": None}),
    )

    passed, diff_table, repro, meta = ep.run_reproduction_guard(client=object(), season=2026, week=1, allow_non_linux=True)
    assert passed is False


def test_guard_fails_when_a_game_is_missing_from_reproduction(monkeypatch):
    stored = _stored([0.51, 0.49, 0.60], ["home", "away", "home"])
    reproduced = _reproduced([0.51, 0.49], ["home", "away"], game_ids=("G1", "G2"))

    monkeypatch.setattr(ep, "load_stored_predictions", lambda client, season, week: stored)
    monkeypatch.setattr(
        ep, "generate_predictions",
        lambda client, season, week, feature_list=None, blend_n=None: (reproduced, {"_model": None}),
    )

    passed, diff_table, repro, meta = ep.run_reproduction_guard(client=object(), season=2026, week=1, allow_non_linux=True)
    assert passed is False


def test_resolve_historical_config_uses_unblended_for_2026_week1():
    from backtests.predict_upcoming import ALL_CURATED_TEAM_FEATURES
    features, blend_n = ep.resolve_historical_config(2026, 1)
    assert features == ALL_CURATED_TEAM_FEATURES


def test_resolve_historical_config_uses_blend_from_week2_onward():
    from backtests.predict_upcoming import PRODUCTION_FEATURE_LIST, PRODUCTION_BLEND_N
    features, blend_n = ep.resolve_historical_config(2026, 2)
    assert features == PRODUCTION_FEATURE_LIST
    assert blend_n == PRODUCTION_BLEND_N


# ── Linux-only guard (2026-09-17: Windows reproduces differently even with ──
# ── identical pinned package versions — see QUESTIONS.md) ──────────────────


def test_guard_refuses_on_non_linux_without_override(monkeypatch):
    monkeypatch.setattr(ep.platform, "system", lambda: "Windows")
    with pytest.raises(SystemExit, match="Refusing to run the reproduction guard"):
        ep.run_reproduction_guard(client=object(), season=2026, week=1)


def test_guard_runs_on_non_linux_with_explicit_override(monkeypatch):
    monkeypatch.setattr(ep.platform, "system", lambda: "Windows")
    stored = _stored([0.51, 0.49, 0.60], ["home", "away", "home"])
    reproduced = _reproduced([0.51, 0.49, 0.60], ["home", "away", "home"])
    monkeypatch.setattr(ep, "load_stored_predictions", lambda client, season, week: stored)
    monkeypatch.setattr(
        ep, "generate_predictions",
        lambda client, season, week, feature_list=None, blend_n=None: (reproduced, {"_model": None}),
    )
    passed, *_ = ep.run_reproduction_guard(client=object(), season=2026, week=1, allow_non_linux=True)
    assert passed is True


def test_check_linux_passes_when_system_is_linux(monkeypatch):
    monkeypatch.setattr(ep.platform, "system", lambda: "Linux")
    ep._check_linux(allow_non_linux=False)  # must not raise


def test_environment_fingerprint_has_expected_keys():
    env = ep.environment_fingerprint()
    assert set(env) == {
        "platform_system", "platform_release", "platform_machine",
        "python_version", "pandas_version", "numpy_version",
        "scikit_learn_version", "xgboost_version",
    }
    assert env["platform_system"] == ep.platform.system()

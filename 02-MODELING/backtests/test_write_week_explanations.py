"""
Unit test for predict_upcoming.write_week_explanations()'s kicked-off-game
guard (STAGE 1.2 test: "explanations are not rewritten for a kicked-off
game"). No BigQuery network calls — the storage functions are monkeypatched.

Run:
    cd 02-MODELING && python -m pytest backtests/test_write_week_explanations.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models.ol_xgb import OLXGBModel  # noqa: E402
from backtests import predict_upcoming as pu  # noqa: E402
import backtests.explanations_bq as explanations_bq  # noqa: E402

FEATURES = ["home_ol_sack_rate", "away_ol_sack_rate", "temp"]


def _fake_meta_and_preds():
    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(size=(3, len(FEATURES))), columns=FEATURES)
    y = pd.Series([0, 1, 0])
    model = OLXGBModel(random_seed=42)
    model.fit(X, y)
    probs = model.predict_proba(X)

    game_ids = ["2026_01_AAA_BBB", "2026_01_CCC_DDD", "2026_01_EEE_FFF"]
    games_meta = pd.DataFrame({
        "game_id": game_ids, "season": 2026, "week": 1,
        "home_team": ["BBB", "DDD", "FFF"], "away_team": ["AAA", "CCC", "EEE"],
    })
    predicted_side = pd.Series(np.where(probs > 0.5, "home", "away"), index=X.index)
    predicted_prob = pd.Series(probs, index=X.index)

    # game_ids[0] has already kicked off (has a recorded result); the other two have not.
    preds = pd.DataFrame({
        "game_id": game_ids,
        "actual_home_covered": [True, None, None],
    })

    meta = {
        "features": FEATURES,
        "blend_n": None,
        "_model": model,
        "_test_X_raw": X,
        "_games_meta": games_meta,
        "_predicted_side": predicted_side,
        "_predicted_home_cover_prob": predicted_prob,
        "_team_features": None,
    }
    return meta, preds, game_ids


def test_kicked_off_game_is_excluded_from_the_write(monkeypatch):
    meta, preds, game_ids = _fake_meta_and_preds()
    captured = {}

    def fake_ensure_table(client):
        captured["ensure_called"] = True

    def fake_delete_kicked_off(client, experiment_id, season, week, kicked_off_game_ids):
        captured["kicked_off_passed_to_delete"] = list(kicked_off_game_ids)

    def fake_write_explanations(client, exp_df, **kwargs):
        captured["written_game_ids"] = set(exp_df["game_id"])
        captured["clean_forward_kwarg"] = kwargs.get("clean_forward")
        return len(exp_df)

    monkeypatch.setattr(explanations_bq, "ensure_explanations_table", fake_ensure_table)
    monkeypatch.setattr(explanations_bq, "delete_kicked_off_games", fake_delete_kicked_off)
    monkeypatch.setattr(explanations_bq, "write_explanations", fake_write_explanations)

    n = pu.write_week_explanations(client=object(), meta=meta, preds=preds, run_id="run-123")

    assert captured["ensure_called"] is True
    assert captured["kicked_off_passed_to_delete"] == [game_ids[0]]
    assert game_ids[0] not in captured["written_game_ids"]
    assert captured["written_game_ids"] == {game_ids[1], game_ids[2]}
    assert n == 2 * len(FEATURES)  # write_explanations returns row count (games x features)


def test_all_games_already_kicked_off_writes_nothing(monkeypatch):
    meta, preds, game_ids = _fake_meta_and_preds()
    preds = preds.assign(actual_home_covered=[True, True, False])

    calls = {"delete": 0, "write": 0}
    monkeypatch.setattr(explanations_bq, "ensure_explanations_table", lambda client: None)
    monkeypatch.setattr(
        explanations_bq, "delete_kicked_off_games",
        lambda *a, **k: calls.__setitem__("delete", calls["delete"] + 1),
    )
    monkeypatch.setattr(
        explanations_bq, "write_explanations",
        lambda *a, **k: calls.__setitem__("write", calls["write"] + 1) or 0,
    )

    n = pu.write_week_explanations(client=object(), meta=meta, preds=preds, run_id="run-456")
    assert n == 0
    assert calls == {"delete": 0, "write": 0}

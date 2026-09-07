"""
Stage 4 tests — the governor.

The acceptance floor from the build plan: across six deliberately flawed
configs it must return non-empty concerns on at least five. That floor exists
because the real failure mode for this layer is not being wrong — it is being
decorative. A governor that says "proceed" to everything teaches the user to
skip it, and is then worse than not having one.

The mirror test matters just as much: a well-designed experiment must come back
clean. A layer that warns about everything is the same failure wearing a
different hat.
"""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_bq_client
from app.main import app
from app.queries import scoping as sq
from app.scoping.governor import (
    SEVERITY_HIGH,
    VERDICT_CAUTION,
    VERDICT_PROCEED,
    VERDICT_RECONSIDER,
    evaluated_games,
    review,
)

GOOD = {
    "name": "sound experiment",
    "target": "ats_cover",
    "features": [{"dataset": "curated", "column": "temp"},
                 {"dataset": "curated", "column": "wind"}],
    "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.53, "min_sample": 500},
    "methodology": {"type": "walk_forward", "train_seasons": 4, "test_seasons": 1,
                    "start_season": 2015, "end_season": 2024, "game_universe": None},
    "model": {"type": "xgboost", "hyperparams": {}},
}
RECORD_OK = {"falsifier": "below 50% ATS across all folds", "mechanism": "heavier OL wins leverage"}


def _cfg(**over):
    c = copy.deepcopy(GOOD)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(c.get(key), dict):
            c[key].update(value)
        else:
            c[key] = value
    return c


# ── the arithmetic ───────────────────────────────────────────────────────────


def test_evaluated_games_counts_folds_not_seasons():
    """
    The number people quote is the season span. The number that matters is
    folds x test seasons x games.
    """
    assert evaluated_games({"start_season": 2015, "end_season": 2024,
                            "train_seasons": 4, "test_seasons": 1}) == 6 * 272


def test_a_design_that_holds_nothing_out_is_caught():
    result = review(_cfg(methodology={"start_season": 2020, "end_season": 2023, "train_seasons": 4}),
                    record_only=RECORD_OK)
    assert any(c["kind"] == "sample_size" and c["severity"] == SEVERITY_HIGH
               for c in result["concerns"])


# ── the mirror test: a good experiment must come back clean ──────────────────


def test_a_sound_experiment_produces_no_concerns():
    """A layer that warns about everything is as useless as one that warns about nothing."""
    result = review(GOOD, record_only=RECORD_OK, prior_configs=[], current_season=2026)
    assert result["concerns"] == []
    assert result["verdict"] == VERDICT_PROCEED


# ── the six flawed fixtures ──────────────────────────────────────────────────


FLAWED = {
    "tiny_slice": (
        _cfg(evaluation={"min_sample": 1500}),
        {"slice_fraction": 0.08},
        "sample_size",
    ),
    "implausible_threshold": (
        _cfg(evaluation={"success_threshold": 0.62}),
        {},
        "implausible_threshold",
    ),
    "unfailable_threshold": (
        _cfg(evaluation={"success_threshold": 0.48}),
        {},
        "trivial_threshold",
    ),
    "slice_is_also_a_feature": (
        _cfg(
            features=[{"dataset": "curated", "column": "div_game"}],
            methodology={"game_universe": {"field": "div_game", "operator": "eq", "value": True}},
        ),
        {},
        "slice_is_feature",
    ),
    "in_progress_season": (
        _cfg(methodology={"end_season": 2026}),
        {"current_season": 2026},
        "cold_start",
    ),
    "no_falsifier": (
        _cfg(),
        {"record_only": {"mechanism": "a hunch"}},
        "no_falsifier",
    ),
}


@pytest.mark.parametrize("label", sorted(FLAWED))
def test_each_flawed_config_is_caught(label):
    config, kwargs, expected_kind = FLAWED[label]
    kwargs = dict(kwargs)
    record_only = kwargs.pop("record_only", RECORD_OK)
    result = review(config, record_only=record_only, prior_configs=[], **kwargs)
    kinds = {c["kind"] for c in result["concerns"]}
    assert expected_kind in kinds, f"{label}: expected {expected_kind}, got {sorted(kinds)}"


def test_governor_clears_the_not_wallpaper_floor():
    """
    The build plan's acceptance criterion, asserted directly: non-empty concerns
    on at least 5 of the 6 flawed fixtures.
    """
    caught = 0
    for _label, (config, kwargs, _kind) in FLAWED.items():
        kwargs = dict(kwargs)
        record_only = kwargs.pop("record_only", RECORD_OK)
        result = review(config, record_only=record_only, prior_configs=[], **kwargs)
        if result["concerns"]:
            caught += 1
    assert caught >= 5, f"governor caught only {caught}/6 — it is becoming decorative"


# ── multiple comparisons ─────────────────────────────────────────────────────


def test_an_identical_prior_run_is_flagged():
    result = review(GOOD, record_only=RECORD_OK, prior_configs=[copy.deepcopy(GOOD)],
                    current_season=2026)
    assert any(c["kind"] == "duplicate_experiment" for c in result["concerns"])


def test_many_near_variants_are_flagged():
    """
    Test twenty variants and one clears 55% by luck. Without this, that one gets
    remembered and the nineteen do not.
    """
    # Each shares temp+wind with GOOD and adds one more: 2 of 3 in common,
    # which is a variant of the same idea rather than a different experiment.
    priors = []
    for column in ("roof_dome", "rest_differential", "div_game", "home_advantage"):
        priors.append(_cfg(features=[{"dataset": "curated", "column": "temp"},
                                     {"dataset": "curated", "column": "wind"},
                                     {"dataset": "curated", "column": column}]))
    result = review(GOOD, record_only=RECORD_OK, prior_configs=priors, current_season=2026)
    concern = next((c for c in result["concerns"] if c["kind"] == "multiple_comparisons"), None)
    assert concern is not None
    assert concern["severity"] == SEVERITY_HIGH


def test_a_different_target_is_not_a_near_variant():
    priors = [_cfg(target="total_over") for _ in range(5)]
    result = review(GOOD, record_only=RECORD_OK, prior_configs=priors, current_season=2026)
    assert not any(c["kind"] == "multiple_comparisons" for c in result["concerns"])


def test_unrecorded_prior_attempts_are_noted():
    result = review(GOOD, record_only={**RECORD_OK, "prior_attempts": "tried this in May"},
                    prior_configs=[], current_season=2026)
    assert any(c["kind"] == "prior_attempts" for c in result["concerns"])


# ── verdicts ─────────────────────────────────────────────────────────────────


def test_two_high_concerns_means_reconsider():
    config = _cfg(evaluation={"success_threshold": 0.62, "min_sample": 99999})
    result = review(config, record_only=RECORD_OK, prior_configs=[], current_season=2026)
    assert result["verdict"] == VERDICT_RECONSIDER


def test_one_high_concern_means_caution():
    result = review(_cfg(evaluation={"success_threshold": 0.62}),
                    record_only=RECORD_OK, prior_configs=[], current_season=2026)
    assert result["verdict"] == VERDICT_CAUTION


# ── the endpoint, and the veto it does not have ──────────────────────────────


class Store:
    def __init__(self):
        self.rows = {}

    def create_session(self, _c, session_id, hypothesis_text):
        self.rows[session_id] = {
            "session_id": session_id, "hypothesis_text": hypothesis_text,
            "slot_answers": {}, "config": None, "config_hash": None,
            "approved_hash": None, "status": "scoping", "experiment_id": None,
        }

    def get_session(self, _c, session_id):
        row = self.rows.get(session_id)
        return dict(row) if row else None

    def update_answers(self, _c, session_id, slot_answers, config, config_hash, status):
        self.rows[session_id].update(slot_answers=slot_answers, config=config,
                                     config_hash=config_hash, status=status, approved_hash=None)

    def set_approved_hash(self, _c, session_id, approved_hash):
        self.rows[session_id].update(approved_hash=approved_hash, status="approved")

    def mark_dispatched(self, _c, session_id, experiment_id):
        self.rows[session_id].update(status="dispatched", experiment_id=experiment_id)


@pytest.fixture
def client(monkeypatch):
    store = Store()
    for fn in ("create_session", "get_session", "update_answers",
               "set_approved_hash", "mark_dispatched"):
        monkeypatch.setattr(sq, fn, getattr(store, fn))
    monkeypatch.setattr(sq, "slice_fraction", lambda *a, **k: None)
    monkeypatch.setattr(sq, "list_prior_configs", lambda *a, **k: [])
    app.dependency_overrides[get_bq_client] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _complete(client):
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "h"}).json()["session_id"]
    while True:
        state = client.get(f"/api/v1/scoping/sessions/{sid}").json()
        q = state["next_question"]
        if q is None:
            return sid
        value = q["default"]
        if value is None:
            if q["type"] == "text":
                value = "a falsifier long enough to count"
            elif q["type"] == "multi_select":
                value = [{"dataset": "curated", "column": "temp", "semantic_name": "temp"}]
        client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                    json={"slot_id": q["slot_id"], "value": value})


def test_review_endpoint_returns_a_verdict(client):
    body = client.get(f"/api/v1/scoping/sessions/{_complete(client)}/review").json()
    assert body["verdict"] in {"proceed", "proceed_with_caution", "reconsider"}
    assert body["advisory_only"] is True
    assert body["evaluated_games"] > 0


def test_review_before_completion_is_409(client):
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "h"}).json()["session_id"]
    assert client.get(f"/api/v1/scoping/sessions/{sid}/review").status_code == 409


def test_a_reconsider_verdict_cannot_stop_a_run(client, monkeypatch):
    """
    The governor advises; Matt decides. If it could veto, it would become a
    thing to route around — and the honest signal would go with the veto.
    """
    from app.routers import scoping as router_mod
    from app.schemas.experiments import ExperimentCreateResponse, ExperimentRunResponse

    monkeypatch.setattr(router_mod, "create_experiment",
                        lambda **kw: ExperimentCreateResponse(experiment_id="exp-9", status="draft"))
    monkeypatch.setattr(router_mod, "trigger_run",
                        lambda **kw: ExperimentRunResponse(run_id="run-9", status="running"))
    monkeypatch.setattr(router_mod.governor, "review",
                        lambda *a, **k: {"concerns": [{"severity": "high", "kind": "x", "message": "no"}],
                                         "verdict": "reconsider"})

    sid = _complete(client)
    assert client.get(f"/api/v1/scoping/sessions/{sid}/review").json()["verdict"] == "reconsider"

    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})
    assert client.post(f"/api/v1/scoping/sessions/{sid}/dispatch").status_code == 202


def test_dispatch_never_calls_the_governor():
    """Structural: the veto is absent, not merely unused."""
    source = open("app/routers/scoping.py", encoding="utf-8").read()
    start = source.index("def dispatch(")
    end = source.index("\n# ──", start)          # the next section marker, whatever it is
    assert "governor" not in source[start:end]

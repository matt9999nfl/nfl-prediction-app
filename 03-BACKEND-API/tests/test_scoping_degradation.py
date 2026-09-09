"""
What the scoping endpoints do when the checks behind them cannot run, and who
is allowed to read them.

F6  a review that could not load its inputs must not look like a clean one
F8  a capability gap that could not be written must be reported, not dropped
Q3  scoping reads carry the API key

The rule all three share: silence must never have the same shape as safety.
A BigQuery outage used to produce a 200 with an empty concern list — identical
to a healthy review of a sound experiment — while degrading toward a LARGER
apparent sample, which is the permissive direction.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_bq_client
from app.main import app
from app.queries import features as fq
from app.queries import scoping as sq
from app.routers import scoping as router_mod

from tests.test_scoping_api import Store, _complete_session

CATALOG = [{"dataset": "curated", "column": "fixture_alpha", "semantic_name": "fixture_alpha"}]


@pytest.fixture
def store(monkeypatch):
    s = Store()
    for fn in ("create_session", "get_session", "update_answers",
               "set_approved_hash", "mark_dispatched"):
        monkeypatch.setattr(sq, fn, getattr(s, fn))
    monkeypatch.setattr(sq, "slice_fraction", lambda *a, **k: None)
    monkeypatch.setattr(sq, "list_prior_configs", lambda *a, **k: [])
    monkeypatch.setattr(sq, "insert_gap", lambda *a, **k: None)
    monkeypatch.setattr(sq, "list_gaps", lambda *a, **k: [])
    monkeypatch.setattr(fq, "list_features", lambda _c: [
        {"semantic_name": "fixture_alpha", "dataset": "curated", "description": ""}])
    return s


@pytest.fixture
def client(store):
    app.dependency_overrides[get_bq_client] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _blow_up(*_a, **_k):
    raise RuntimeError("simulated BigQuery outage")


# ── FINDING HC-S6-F6: a check that could not run is not a check that passed ──


def test_a_review_that_could_not_load_its_inputs_says_so(client, monkeypatch):
    monkeypatch.setattr(sq, "slice_fraction", _blow_up)
    monkeypatch.setattr(sq, "list_prior_configs", _blow_up)

    sid = _complete_session(client)
    body = client.get(f"/api/v1/scoping/sessions/{sid}/review").json()

    assert body["degraded"] is True
    assert set(body["checks_unavailable"]) == {"prior_configs", "slice_fraction"}
    outages = [c for c in body["concerns"] if c["kind"] == "upstream_error"]
    assert len(outages) == 2, f"the outage was not reported: {body['concerns']}"
    assert any("slice" in c["message"] or "game-universe" in c["message"] for c in outages)
    assert any("saved experiments" in c["message"] for c in outages)


def test_a_review_that_could_not_run_never_returns_proceed(client, monkeypatch):
    """
    The verdict is the part a user acts on. An outage must not be able to
    produce the same word as a sound experiment.
    """
    monkeypatch.setattr(sq, "slice_fraction", _blow_up)
    monkeypatch.setattr(sq, "list_prior_configs", _blow_up)

    sid = _complete_session(client)
    body = client.get(f"/api/v1/scoping/sessions/{sid}/review").json()
    assert body["verdict"] != "proceed", (
        "a review that checked neither the sample size nor the prior runs "
        "returned a clean bill of health"
    )


def test_one_failed_input_is_still_reported(client, monkeypatch):
    """Partial availability is still partial. The half that did not run is named."""
    monkeypatch.setattr(sq, "list_prior_configs", _blow_up)

    sid = _complete_session(client)
    body = client.get(f"/api/v1/scoping/sessions/{sid}/review").json()
    assert body["checks_unavailable"] == ["prior_configs"]
    assert body["verdict"] != "proceed"


def test_a_healthy_review_is_not_made_noisy(client):
    """
    The other half of the contract: a layer that warns about everything is as
    useless as one that warns about nothing. Nothing failed here, so nothing
    about an outage may appear.
    """
    sid = _complete_session(client)
    body = client.get(f"/api/v1/scoping/sessions/{sid}/review").json()
    assert body["degraded"] is False
    assert body["checks_unavailable"] == []
    assert not [c for c in body["concerns"] if c["kind"] == "upstream_error"]


def test_a_failed_slice_count_warns_that_the_reported_sample_is_the_unsliced_one(
    client, monkeypatch, store
):
    """
    The specific danger in F6: with the count unavailable, `evaluated_games`
    reports the UNSLICED figure, which is larger than the truth. The user must
    be told that, or the number reads as a reassurance.
    """
    monkeypatch.setattr(sq, "slice_fraction", _blow_up)
    sid = _complete_session(client)
    store.rows[sid]["slot_answers"]["game_universe"] = {
        "field": "div_game", "operator": "eq", "value": True}

    body = client.get(f"/api/v1/scoping/sessions/{sid}/review").json()
    outage = next(c for c in body["concerns"] if c["kind"] == "upstream_error")
    assert "overstates" in outage["message"]
    assert body["evaluated_games"] > 0


# ── FINDING HC-S6-F8: a gap that could not be written is still a gap ─────────


@pytest.fixture
def extraction(monkeypatch):
    monkeypatch.setattr(router_mod, "extract_slots", lambda **kw: {
        "slot_prefills": {},
        "unmatched_concepts": ["average offensive line weight"],
        "requested_slices": [],
    })


def test_a_gap_that_cannot_be_written_is_reported(client, monkeypatch, extraction):
    monkeypatch.setattr(sq, "insert_gap", _blow_up)

    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "ol weight matters"}).json()["session_id"]
    body = client.post(f"/api/v1/scoping/sessions/{sid}/extract").json()

    assert body["gaps"] == [], "a gap that was never written is not a recorded gap"
    assert len(body["gaps_not_recorded"]) == 1, (
        "the failed write was dropped: 'the gap write failed' and 'there are no "
        "gaps' reach the caller as the same answer"
    )
    assert body["gaps_not_recorded"][0]["status"] == "not_recorded"
    assert "not_recorded" in (body["detail"] or "") or "could not be written" in (body["detail"] or "")


def test_a_written_gap_is_reported_as_written(client, extraction):
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "ol weight matters"}).json()["session_id"]
    body = client.post(f"/api/v1/scoping/sessions/{sid}/extract").json()

    assert len(body["gaps"]) == 1
    assert body["gaps"][0]["status"] == "open"
    assert body["gaps_not_recorded"] == []
    assert body["detail"] is None


def test_a_gap_write_failure_does_not_block_the_session(client, monkeypatch, extraction):
    """Stage 3 is additive; it cannot stop a session reaching a run."""
    monkeypatch.setattr(sq, "insert_gap", _blow_up)
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "ol weight matters"}).json()["session_id"]
    assert client.post(f"/api/v1/scoping/sessions/{sid}/extract").status_code == 200


# ── HC-S6 Q3: the read surface is not public ─────────────────────────────────


READ_PATHS = [
    "/api/v1/scoping/capability-gaps",
    "/api/v1/scoping/sessions/{sid}",
    "/api/v1/scoping/sessions/{sid}/brief",
    "/api/v1/scoping/sessions/{sid}/review",
]


@pytest.fixture
def keyed(monkeypatch):
    """Production mode: OWNER_API_KEY configured."""
    monkeypatch.setattr(settings, "owner_api_key", "test-owner-key")
    return {"X-API-Key": "test-owner-key"}


@pytest.mark.parametrize("path", READ_PATHS)
def test_an_anonymous_caller_cannot_read_a_scoping_endpoint(client, keyed, path):
    """
    A session carries the hypothesis, every answer and the assembled config;
    the gap list is a readable index of what the platform cannot do. Neither is
    the public predictions surface the open-read convention was written for.
    """
    sid = _complete_session_with_key(client, keyed)
    r = client.get(path.format(sid=sid))
    assert r.status_code == 401, f"{path} answered an anonymous caller: {r.status_code}"
    assert r.json()["code"] == "unauthorized"


@pytest.mark.parametrize("path", READ_PATHS)
def test_the_key_holder_still_reads_everything(client, keyed, path):
    sid = _complete_session_with_key(client, keyed)
    r = client.get(path.format(sid=sid), headers=keyed)
    assert r.status_code == 200, r.text


def test_an_unknown_session_is_404_for_the_key_holder_not_401(client, keyed):
    r = client.get("/api/v1/scoping/sessions/nope", headers=keyed)
    assert r.status_code == 404


def _complete_session_with_key(client, headers) -> str:
    """_complete_session, but authenticated — the writes need the key too."""
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "auth probe"},
                      headers=headers).json()["session_id"]
    while True:
        state = client.get(f"/api/v1/scoping/sessions/{sid}", headers=headers).json()
        q = state["next_question"]
        if q is None:
            return sid
        value = q["default"]
        if value is None:
            if q["type"] == "text":
                value = f"answer for {q['slot_id']}"
            elif q["type"] == "multi_select":
                value = CATALOG
        r = client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                        json={"slot_id": q["slot_id"], "value": value}, headers=headers)
        assert r.status_code == 200, r.text

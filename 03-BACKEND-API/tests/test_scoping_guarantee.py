"""
The approval guarantee after HC-S6 — the three holes, closed and pinned.

F2  the approved artefact is the WHOLE brief, not the config half of it
F10 an approval that lost a race does not land
Q2  dispatch can be rehearsed without creating anything

Each test here is written so that reverting its fix turns it red. Where the
fake store is used, it derives its behaviour from the real SQL — see the module
docstring of test_scoping_api.py for why that matters.
"""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_bq_client
from app.main import app
from app.queries import scoping as sq
from app.routers import scoping as router_mod
from app.schemas.experiments import ExperimentCreateResponse, ExperimentRunResponse
from app.scoping.hashing import approval_hash, config_hash

from tests.test_scoping_api import Store, _complete_session


@pytest.fixture
def store(monkeypatch):
    s = Store()
    for fn in ("create_session", "get_session", "update_answers",
               "set_approved_hash", "mark_dispatched"):
        monkeypatch.setattr(sq, fn, getattr(s, fn))
    return s


@pytest.fixture
def dispatched(monkeypatch):
    calls = {"created": [], "ran": []}
    monkeypatch.setattr(router_mod, "create_experiment",
                        lambda *, body, request, request_id, bq, _: (
                            calls["created"].append(body.model_dump())
                            or ExperimentCreateResponse(experiment_id="exp-1", status="draft")))
    monkeypatch.setattr(router_mod, "trigger_run",
                        lambda *, experiment_id, request, request_id, bq, _: (
                            calls["ran"].append(experiment_id)
                            or ExperimentRunResponse(run_id="run-1", status="running")))
    return calls


@pytest.fixture
def client(store):
    app.dependency_overrides[get_bq_client] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _approve(client, sid) -> str:
    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    r = client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})
    assert r.status_code == 200, r.text
    return h


# ── FINDING HC-S6-F2: the hash covers everything the brief renders ───────────


def test_the_approval_hash_moves_when_a_record_only_answer_moves():
    """
    The unit form. `config_hash` covers the config; `approval_hash` covers the
    document. The falsifier is rendered into the brief and held by no config
    field, so hashing the config alone left it free to change after approval.
    """
    payload = {"name": "x", "evaluation": {"min_sample": 500}}
    before = {"mechanism": "market lag", "falsifier": "below 50% ATS in every fold"}
    after = {"mechanism": "market lag", "falsifier": "nothing would change my mind"}

    assert config_hash(payload) == config_hash(payload)
    assert approval_hash(payload, before) != approval_hash(payload, after), (
        "the falsifier changed and the approval hash did not — dispatch would "
        "proceed against a document nobody approved"
    )


def test_a_record_only_answer_cannot_be_smuggled_into_the_config_half():
    """The two halves are labelled, so no arrangement of one can imitate the other."""
    assert approval_hash({"record_only": {"falsifier": "a"}}, {}) != \
           approval_hash({}, {"falsifier": "a"})


def test_changing_only_the_falsifier_invalidates_a_surviving_approval(client, store, dispatched):
    """
    ATTACK, and the second half of F2.

    F1 now clears the stored approval on any answer, so this attack is already
    refused. To prove F2 closes the hole on its OWN, the stored approval is put
    back by hand after the falsifier changes — exactly the state F1 used to
    leave behind — and dispatch must still refuse.
    """
    sid = _complete_session(client)
    _approve(client, sid)
    stale_approval = store.rows[sid]["approved_hash"]
    assert stale_approval

    r = client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                    json={"slot_id": "falsifier", "value": "nothing would change my mind"})
    assert r.status_code == 200
    assert store.rows[sid]["approved_hash"] is None, "F1 regression: the approval survived"

    # Re-attach it: the exact state the unfixed UPDATE used to leave.
    store.rows[sid]["approved_hash"] = stale_approval

    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "approval_mismatch"
    assert dispatched["created"] == [], "an experiment ran against an unapproved brief"


def test_the_config_half_is_still_caught(client, store, dispatched):
    """The half that already worked must keep working."""
    sid = _complete_session(client)
    _approve(client, sid)
    stale_approval = store.rows[sid]["approved_hash"]

    client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                json={"slot_id": "min_sample", "value": 12345})
    store.rows[sid]["approved_hash"] = stale_approval

    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    assert r.status_code == 409
    assert r.json()["code"] == "approval_mismatch"
    assert dispatched["created"] == []


# ── FINDING HC-S6-F10: a lost race writes nothing and says so ────────────────


def test_an_approval_that_lost_a_race_is_refused_with_409(client, store, monkeypatch):
    """
    ATTACK: land an answer between approve's read and approve's write.

    The interleaving is forced rather than raced, so the test is deterministic:
    the store's write is wrapped in a function that applies the competing answer
    first. Without the condition on the UPDATE the approval lands anyway,
    attached to answers it was not computed from, and dispatch then refuses
    forever with nothing to explain why.
    """
    sid = _complete_session(client)
    real_write = store.set_approved_hash

    def race(_c, session_id, approved_hash, expected_config_hash=None):
        # The competing answer, landing first.
        answers = dict(store.rows[session_id]["slot_answers"])
        answers["min_sample"] = 999
        from app.scoping.assemble import assemble
        from app.scoping.schema import load_tree
        payload = assemble(load_tree(), answers)
        store.update_answers(_c, session_id, answers, payload, config_hash(payload), "assembled")
        return real_write(_c, session_id, approved_hash, expected_config_hash)

    monkeypatch.setattr(sq, "set_approved_hash", race)

    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    r = client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})

    assert r.status_code == 409, r.text
    assert r.json()["code"] == "approval_conflict"
    assert store.rows[sid]["approved_hash"] is None, (
        "the approval landed on answers it was not computed from; the session is "
        "wedged and nothing says why"
    )


def test_the_message_tells_the_user_what_to_do(client, store, monkeypatch):
    """A 409 nobody can act on is the wedge with a status code on it."""
    sid = _complete_session(client)
    real_write = store.set_approved_hash
    monkeypatch.setattr(sq, "set_approved_hash",
                        lambda *a, **k: False)
    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    body = client.post(f"/api/v1/scoping/sessions/{sid}/approve",
                       json={"config_hash": h}).json()
    assert "approve again" in body["error"].lower()


# ── HC-S6 Q2: dry-run dispatch ───────────────────────────────────────────────


def test_dry_run_dispatch_writes_nothing(client, store, dispatched):
    """
    Acceptance: "Dry-run dispatch writes nothing — asserted by row counts before
    and after." The store is the rows; it is compared whole, so a changed
    status or a set experiment_id counts as a write too.
    """
    sid = _complete_session(client)
    _approve(client, sid)

    before = copy.deepcopy(store.rows)
    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch?dry_run=true")

    assert r.status_code == 200, r.text
    assert store.rows == before, "dry-run dispatch changed the session store"
    assert dispatched["created"] == [], "dry-run dispatch created an experiment"
    assert dispatched["ran"] == [], "dry-run dispatch fired the runner"


def test_dry_run_returns_the_payload_it_would_have_created(client, store, dispatched):
    """The point of the mode: see the experiment without minting one."""
    sid = _complete_session(client)
    _approve(client, sid)

    dry = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch?dry_run=true").json()
    assert dry["dry_run"] is True
    assert dry["status"] == "not_dispatched"
    assert dry["would_create"]["name"]
    assert dry["config_hash"] == config_hash(store.rows[sid]["config"])

    real = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    assert real.status_code == 202
    assert dispatched["created"][0] == dry["would_create"], (
        "the dry run described an experiment other than the one that ran"
    )


def test_dry_run_runs_every_check_rather_than_skipping_them(client, dispatched):
    """
    A rehearsal that skips the guards rehearses nothing. An unapproved session
    must fail the dry run exactly as it fails the real one.
    """
    sid = _complete_session(client)
    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch?dry_run=true")
    assert r.status_code == 409
    assert r.json()["code"] == "not_approved"


def test_dry_run_refuses_a_brief_that_changed_after_approval(client, store, dispatched):
    sid = _complete_session(client)
    _approve(client, sid)
    stale = store.rows[sid]["approved_hash"]
    client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                json={"slot_id": "falsifier", "value": "nothing at all"})
    store.rows[sid]["approved_hash"] = stale

    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch?dry_run=true")
    assert r.status_code == 409
    assert r.json()["code"] == "approval_mismatch"


def test_a_dry_run_does_not_consume_the_session(client, store, dispatched):
    """Rehearse, then run for real. The dry run must not be the dispatch."""
    sid = _complete_session(client)
    _approve(client, sid)
    for _ in range(3):
        assert client.post(f"/api/v1/scoping/sessions/{sid}/dispatch?dry_run=true").status_code == 200
    assert client.post(f"/api/v1/scoping/sessions/{sid}/dispatch").status_code == 202
    assert len(dispatched["created"]) == 1


# ── HC-S6-FIX-Q5 stopgap: the approve-time window, closed for clients that ask ─


def test_a_client_that_sends_the_brief_hash_is_told_at_approve_time(client, store):
    """
    The window option (a) leaves open, and the one line that closes it.

    Render the brief, change the falsifier, then approve with the hashes the
    brief gave. `config_hash` cannot see a record-only change, so on its own it
    would let the approval through and the user would be signing a document
    they never read. `approval_hash` catches it here.
    """
    sid = _complete_session(client)
    brief = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()

    client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                json={"slot_id": "falsifier", "value": "nothing would change my mind"})

    r = client.post(f"/api/v1/scoping/sessions/{sid}/approve",
                    json={"config_hash": brief["config_hash"],
                          "approval_hash": brief["approval_hash"]})
    assert r.status_code == 409
    assert r.json()["code"] == "stale_brief"
    assert store.rows[sid]["approved_hash"] is None


def test_without_the_brief_hash_the_window_is_still_open_at_approve_time(client, store):
    """
    Recorded, not celebrated. A client that sends only `config_hash` — every
    client written before this change — still gets the approval through, and the
    mismatch is only caught at dispatch. That is the residual cost of leaving
    render() untouched, and it is what HC-S6-FIX-Q5 asks PROJECT-LEAD to rule on.
    """
    sid = _complete_session(client)
    brief = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()
    client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                json={"slot_id": "falsifier", "value": "nothing would change my mind"})

    r = client.post(f"/api/v1/scoping/sessions/{sid}/approve",
                    json={"config_hash": brief["config_hash"]})
    assert r.status_code == 200, "behaviour changed — re-read HC-S6-FIX-Q5"
    # The approval that landed is over the CURRENT answers, so dispatch proceeds
    # against a document the user did not read. Caught only by them re-reading it.
    assert store.rows[sid]["approved_hash"] != brief["approval_hash"]


def test_the_brief_reports_both_hashes(client):
    sid = _complete_session(client)
    brief = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()
    assert len(brief["approval_hash"]) == 64
    assert brief["approval_hash"] != brief["config_hash"]
    assert brief["config_hash"] in brief["brief_markdown"], (
        "the hash printed in the document is still the config hash — render() "
        "output is unchanged, per the HC-S6-FIX kill-switch"
    )
    assert brief["approval_hash"] not in brief["brief_markdown"]

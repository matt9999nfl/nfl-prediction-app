"""
Stage 2 endpoint tests — the approval guarantee, end to end.

BigQuery is replaced with an in-memory store and the experiment write path with
a recorder, so a whole session runs without GCP.  What is being tested is the
guarantee itself: an experiment cannot start unless the exact config that will
run is the one that was approved.

WHY THE STORE BELOW READS THE REAL SQL
--------------------------------------
FINDING HC-S6-F1.  This stand-in used to clear `approved_hash` in its
`update_answers` while the real UPDATE in app/queries/scoping.py never touched
the column.  `test_changing_an_answer_after_approval_blocks_dispatch` passed on
the strength of that difference — the one test guarding the feature's core
guarantee was green because the fake was kinder than production, while the
guarantee itself was broken in the live service.

Fixing the SQL alone would leave the fake making its own independent claim, and
the test would stay green through a regression.  So the fake no longer claims
anything: `_real_update_clears_approved_hash()` reads the SET clause of the
actual statement, and the stand-in behaves the way that statement behaves.
Revert the SQL and this file goes red.

The rule this encodes: a fake may only be as kind as the thing it stands in for.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_bq_client
from app.main import app
from app.queries import scoping as sq
from app.routers import scoping as router_mod
from app.schemas.experiments import ExperimentCreateResponse, ExperimentRunResponse
from app.scoping.schema import load_tree

CATALOG = [{"dataset": "curated", "column": "fixture_alpha", "semantic_name": "Fixture Alpha"}]


# Read from the FILE, not from the module attribute: the `store` fixture below
# monkeypatches these names onto app.queries.scoping, so anything reading the
# attribute at test time would end up reading this fake's own source and
# confirming itself.
_QUERIES_SRC = Path(sq.__file__).read_text(encoding="utf-8")


def _sql_of(function_name: str) -> str:
    """
    The statement a query function issues — not its docstring, and not its
    parameter names, either of which can mention a column the SQL does not
    touch. The table name is interpolated, so the statement is an f-string and
    its literal parts are stitched back together.
    """
    for node in ast.walk(ast.parse(_QUERIES_SRC)):
        if not (isinstance(node, ast.FunctionDef) and node.name == function_name):
            continue
        statements = []
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                statements.append(child.value)
            elif isinstance(child, ast.JoinedStr):
                statements.append("".join(
                    part.value if isinstance(part, ast.Constant) else "?"
                    for part in child.values
                ))
        found = [t for t in statements
                 if t.strip().upper().startswith(("UPDATE ", "INSERT ", "SELECT "))]
        assert found, f"{function_name} issues no statement"
        return max(found, key=len)
    raise AssertionError(f"app/queries/scoping.py has no function {function_name!r}")


def _real_update_clears_approved_hash() -> bool:
    """Does the statement app/queries/scoping.py actually issues clear it?"""
    sql = _sql_of("update_answers")
    set_clause = sql[sql.upper().index("SET"):sql.upper().index("WHERE")]
    return "approved_hash" in set_clause


def _real_approval_is_conditional() -> bool:
    """Does set_approved_hash condition its write on the config hash?"""
    sql = _sql_of("set_approved_hash")
    return "config_hash" in sql[sql.upper().index("WHERE"):]


class Store:
    """
    Minimal stand-in for platform.scoping_sessions.

    Every behaviour that the approval guarantee rests on is read from the real
    SQL rather than restated here.  See the module docstring.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

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
        self.rows[session_id].update(
            slot_answers=slot_answers, config=config, config_hash=config_hash,
            status=status,
        )
        if _real_update_clears_approved_hash():
            self.rows[session_id].update(approved_hash=None)

    def set_approved_hash(self, _c, session_id, approved_hash, expected_config_hash=None):
        expected = expected_config_hash if expected_config_hash is not None else approved_hash
        if _real_approval_is_conditional() and self.rows[session_id].get("config_hash") != expected:
            return False       # zero rows changed: the condition matched nothing
        self.rows[session_id].update(approved_hash=approved_hash, status="approved")
        return True

    def mark_dispatched(self, _c, session_id, experiment_id):
        self.rows[session_id].update(status="dispatched", experiment_id=experiment_id)


@pytest.fixture
def store(monkeypatch):
    s = Store()
    for fn in ("create_session", "get_session", "update_answers",
               "set_approved_hash", "mark_dispatched"):
        monkeypatch.setattr(sq, fn, getattr(s, fn))
    return s


@pytest.fixture
def dispatched(monkeypatch):
    """Records calls into the wizard's own create/trigger handlers."""
    calls = {"created": [], "ran": []}

    def fake_create(*, body, request, request_id, bq, _):
        calls["created"].append(body.model_dump())
        return ExperimentCreateResponse(experiment_id="exp-1", status="draft")

    def fake_run(*, experiment_id, request, request_id, bq, _):
        calls["ran"].append(experiment_id)
        return ExperimentRunResponse(run_id="run-1", status="running")

    monkeypatch.setattr(router_mod, "create_experiment", fake_create)
    monkeypatch.setattr(router_mod, "trigger_run", fake_run)
    return calls


@pytest.fixture
def client(store):
    app.dependency_overrides[get_bq_client] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _complete_session(client) -> str:
    """Walk a full session: start, then answer every question the server asks."""
    r = client.post("/api/v1/scoping/sessions", json={"hypothesis_text": "OL weight in bad weather"})
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]

    while True:
        state = client.get(f"/api/v1/scoping/sessions/{sid}").json()
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
                        json={"slot_id": q["slot_id"], "value": value})
        assert r.status_code == 200, r.text


# ── the happy path ───────────────────────────────────────────────────────────


def test_a_session_walks_to_an_assembled_config(client):
    sid = _complete_session(client)
    state = client.get(f"/api/v1/scoping/sessions/{sid}").json()
    assert state["status"] == "assembled"
    assert state["config"] is not None
    assert len(state["config_hash"]) == 64
    assert state["missing_required"] == []


def test_brief_matches_the_hash_the_state_reports(client):
    sid = _complete_session(client)
    state = client.get(f"/api/v1/scoping/sessions/{sid}").json()
    brief = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()
    assert brief["config_hash"] == state["config_hash"]
    assert brief["config_hash"] in brief["brief_markdown"]


def test_approve_then_dispatch_runs_the_experiment(client, dispatched):
    sid = _complete_session(client)
    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]

    assert client.post(f"/api/v1/scoping/sessions/{sid}/approve",
                       json={"config_hash": h}).status_code == 200
    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    assert r.status_code == 202, r.text
    assert r.json()["experiment_id"] == "exp-1"
    assert dispatched["ran"] == ["exp-1"]


def test_dispatch_sends_the_approved_config_unchanged(client, dispatched):
    """
    What runs must be the experiment that was described in the brief.

    Compared after validation on both sides: the stored config omits optional
    slots left blank (so Pydantic applies its own defaults), while model_dump()
    on the dispatched body materialises them as explicit nulls. Those are the
    same experiment, and comparing the raw dicts would fail on that difference
    alone while catching nothing real.
    """
    sid = _complete_session(client)
    state = client.get(f"/api/v1/scoping/sessions/{sid}").json()
    h = state["config_hash"]
    client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})
    client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")

    from app.schemas.experiments import ExperimentCreateRequest
    approved = ExperimentCreateRequest.model_validate(state["config"]).model_dump()
    assert dispatched["created"][0] == approved


# ── the guarantee ────────────────────────────────────────────────────────────


def test_dispatch_without_approval_is_refused(client, dispatched):
    sid = _complete_session(client)
    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    assert r.status_code == 409
    assert r.json()["code"] == "not_approved"
    assert dispatched["created"] == [], "an unapproved experiment was created"


def test_changing_an_answer_after_approval_blocks_dispatch(client, dispatched):
    """
    The failure this whole design exists to prevent: approve one thing, run
    another. Approve, then alter an answer, then try to run.
    """
    sid = _complete_session(client)
    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})

    client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                json={"slot_id": "min_sample", "value": 12345})

    r = client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    assert r.status_code == 409
    assert r.json()["code"] in ("not_approved", "approval_mismatch")
    assert dispatched["created"] == [], "a config was run that nobody approved"


def test_approving_a_stale_hash_is_refused(client):
    sid = _complete_session(client)
    r = client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": "0" * 64})
    assert r.status_code == 409
    assert r.json()["code"] == "stale_brief"


def test_dispatching_twice_is_refused(client, dispatched):
    sid = _complete_session(client)
    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})
    assert client.post(f"/api/v1/scoping/sessions/{sid}/dispatch").status_code == 202
    assert client.post(f"/api/v1/scoping/sessions/{sid}/dispatch").status_code == 409
    assert len(dispatched["created"]) == 1


def test_answering_after_dispatch_is_refused(client, dispatched):
    sid = _complete_session(client)
    h = client.get(f"/api/v1/scoping/sessions/{sid}/brief").json()["config_hash"]
    client.post(f"/api/v1/scoping/sessions/{sid}/approve", json={"config_hash": h})
    client.post(f"/api/v1/scoping/sessions/{sid}/dispatch")
    r = client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                    json={"slot_id": "name", "value": "renamed"})
    assert r.status_code == 409


# ── error surfaces ───────────────────────────────────────────────────────────


def test_brief_before_completion_is_409(client):
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "h"}).json()["session_id"]
    r = client.get(f"/api/v1/scoping/sessions/{sid}/brief")
    assert r.status_code == 409
    assert r.json()["code"] == "incomplete_scoping"


def test_unknown_session_is_404(client):
    assert client.get("/api/v1/scoping/sessions/nope").status_code == 404


def test_unknown_slot_is_400(client):
    sid = client.post("/api/v1/scoping/sessions",
                      json={"hypothesis_text": "h"}).json()["session_id"]
    r = client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                    json={"slot_id": "nope", "value": 1})
    assert r.status_code == 400
    assert r.json()["code"] == "unknown_slot"


def test_first_question_is_the_first_slot_in_the_tree(client):
    r = client.post("/api/v1/scoping/sessions", json={"hypothesis_text": "h"})
    assert r.json()["next_question"]["slot_id"] == load_tree().slots[0].id


def test_prefills_start_unconfirmed(client):
    """Stage 3 will populate these. The contract that they are never answers starts here."""
    q = client.post("/api/v1/scoping/sessions", json={"hypothesis_text": "h"}).json()["next_question"]
    assert q["confirmed"] is False
    assert q["prefill"] is None

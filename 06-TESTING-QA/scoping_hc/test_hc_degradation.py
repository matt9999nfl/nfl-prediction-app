"""
Requirement E — degradation.

Two failure modes, both required by the brief:

  * ANTHROPIC_API_KEY unset — extraction must report itself unavailable and a
    session must still reach a dispatched run.
  * BigQuery raising — what the endpoints actually do when a query blows up.

On the harness. These tests inject FAULTS; they do not stand in for storage.
Where a session has to exist for the fault to be reachable at all, the session
store is a recorder and that is stated in the test. No test here claims to be
evidence that the flow works against live BigQuery — that claim belongs to
integration/test_hypothesis_chat.py and to nothing else.
"""
from __future__ import annotations

import ast

import pytest

fastapi_testclient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi not installed in this environment"
)
TestClient = fastapi_testclient.TestClient

pytestmark = pytest.mark.integration


def _error_code(response) -> str:
    """
    The app flattens HTTPException detail into the ErrorResponse envelope
    (app/main.py::http_exception_handler), so the code is top-level. Read both
    shapes so this does not become a test of the envelope.
    """
    body = response.json()
    if isinstance(body, dict) and "code" in body:
        return body["code"]
    return body["detail"]["code"]


class Exploding:
    """A BigQuery client whose every query raises, as one would mid-incident."""

    def __init__(self, message="simulated BigQuery outage"):
        self.message = message
        self.calls = 0

    def query(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError(self.message)


class RecordingStore:
    """
    Session bookkeeping only.

    Present so a fault in a DIFFERENT query is reachable. It is not a storage
    stand-in for any behavioural claim in this module.
    """

    def __init__(self):
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
        # Mirrors the REAL UPDATE, which does not touch approved_hash.
        # See FINDING HC-S6-F1.
        self.rows[session_id].update(
            slot_answers=slot_answers, config=config,
            config_hash=config_hash, status=status,
        )

    def set_approved_hash(self, _c, session_id, approved_hash):
        self.rows[session_id].update(approved_hash=approved_hash, status="approved")

    def mark_dispatched(self, _c, session_id, experiment_id):
        self.rows[session_id].update(status="dispatched", experiment_id=experiment_id)


@pytest.fixture
def app_module(backend_root):
    import sys
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app import main
    return main


@pytest.fixture
def exploding_client(app_module):
    from app.dependencies import get_bq_client
    exploding = Exploding()
    app_module.app.dependency_overrides[get_bq_client] = lambda: exploding
    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        yield client, exploding
    app_module.app.dependency_overrides.clear()


# ── BigQuery raising ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/scoping/capability-gaps"),
        ("GET", "/api/v1/scoping/sessions/00000000-0000-0000-0000-000000000000"),
        ("GET", "/api/v1/scoping/sessions/00000000-0000-0000-0000-000000000000/brief"),
        ("GET", "/api/v1/scoping/sessions/00000000-0000-0000-0000-000000000000/review"),
    ],
)
def test_a_raising_bigquery_surfaces_as_502_not_500_and_not_a_wrong_answer(
    exploding_client, method, path
):
    """
    A crash is honest; a 500 with a stack trace or a 200 with empty data is not.

    Every read here must come back 502 upstream_error, so the caller can tell
    "the store is down" from "there is nothing there".
    """
    client, exploding = exploding_client
    response = client.request(method, path)
    assert response.status_code == 502, (
        f"{method} {path} returned {response.status_code}: {response.text[:300]}"
    )
    assert _error_code(response) == "upstream_error"
    assert exploding.calls > 0, "the endpoint never reached BigQuery at all"


def test_creating_a_session_against_a_raising_bigquery_is_502(exploding_client):
    client, _ = exploding_client
    response = client.post(
        "/api/v1/scoping/sessions", json={"hypothesis_text": "outage probe"}
    )
    assert response.status_code == 502
    assert _error_code(response) == "upstream_error"


# ── FINDING HC-S6-F6, live ───────────────────────────────────────────────────


def test_review_hides_a_bigquery_outage_behind_a_normal_looking_verdict(
    app_module, monkeypatch
):
    """
    FINDING HC-S6-F6 (the live half). See also
    test_hc_governor_arithmetic.py::test_a_failed_slice_count_is_reported_as_if_no_slice_were_applied.

    /review catches failures from BOTH sq.slice_fraction and
    sq.list_prior_configs, logs a warning, and carries on. The response is a
    200 with a verdict, a null slice_fraction and an empty concern list — the
    same shape as a healthy review of a sound experiment.

    So during a BigQuery outage the governor tells the user their experiment is
    fine, having checked neither the sample size nor the prior runs. The
    dashboard stays green while the job stops being done.
    """
    from app.dependencies import get_bq_client
    from app.queries import scoping as sq
    from app.routers import scoping as router_mod

    store = RecordingStore()
    for name in ("create_session", "get_session", "update_answers",
                 "set_approved_hash", "mark_dispatched"):
        monkeypatch.setattr(sq, name, getattr(store, name))

    def blow_up(*_a, **_k):
        raise RuntimeError("simulated BigQuery outage")

    monkeypatch.setattr(sq, "slice_fraction", blow_up)
    monkeypatch.setattr(sq, "list_prior_configs", blow_up)

    app_module.app.dependency_overrides[get_bq_client] = lambda: object()
    try:
        with TestClient(app_module.app, raise_server_exceptions=False) as client:
            session_id = _walk_a_complete_session(client)
            response = client.get(f"/api/v1/scoping/sessions/{session_id}/review")
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slice_fraction"] is None
    assert body["verdict"] in {"proceed", "proceed_with_caution", "reconsider"}
    assert "degraded" not in response.text.lower(), (
        "the response now signals degradation — F6 may be closed"
    )
    assert not any(c["kind"] == "upstream_error" for c in body["concerns"]), (
        "the outage is now reported as a concern — F6 may be closed"
    )


CATALOG = [{"dataset": "curated", "column": "fixture_alpha", "semantic_name": "fixture_alpha"}]


def _walk_a_complete_session(client, hypothesis="degradation probe") -> str:
    response = client.post("/api/v1/scoping/sessions", json={"hypothesis_text": hypothesis})
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]
    while True:
        state = client.get(f"/api/v1/scoping/sessions/{session_id}").json()
        question = state["next_question"]
        if question is None:
            return session_id
        value = question["default"]
        if value is None:
            if question["type"] == "text":
                value = f"answer for {question['slot_id']}"
            elif question["type"] == "multi_select":
                value = CATALOG
        response = client.post(
            f"/api/v1/scoping/sessions/{session_id}/answers",
            json={"slot_id": question["slot_id"], "value": value},
        )
        assert response.status_code == 200, response.text


# ── no Anthropic key ─────────────────────────────────────────────────────────


def test_extraction_reports_itself_unavailable_without_a_key(backend_root, monkeypatch):
    """The contract the whole 60/30/10 split rests on: no key, no blockage."""
    import sys
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app.claude_scoping import ClaudeScopingError, extract_slots

    with pytest.raises(ClaudeScopingError) as caught:
        extract_slots(api_key="", model="claude-haiku-4-5",
                      hypothesis_text="anything", slots=[], catalog=[])
    assert "ANTHROPIC_API_KEY" in str(caught.value)


def test_a_session_completes_and_dispatches_with_no_anthropic_key(
    app_module, monkeypatch
):
    """
    Stage 2 is the load-bearing layer: with the key unset the session must
    still reach a dispatched run.

    The experiment write path is recorded rather than executed, because
    dispatching for real fires the production experiment-runner Cloud Run job.
    See the escalation in HYPOTHESIS-CHAT-QUESTIONS.md.
    """
    from app.config import settings
    from app.dependencies import get_bq_client
    from app.queries import scoping as sq
    from app.routers import scoping as router_mod
    from app.schemas.experiments import ExperimentCreateResponse, ExperimentRunResponse

    monkeypatch.setattr(settings, "anthropic_api_key", "")

    store = RecordingStore()
    for name in ("create_session", "get_session", "update_answers",
                 "set_approved_hash", "mark_dispatched"):
        monkeypatch.setattr(sq, name, getattr(store, name))

    created: list[dict] = []
    monkeypatch.setattr(
        router_mod, "create_experiment",
        lambda *, body, request, request_id, bq, _: (
            created.append(body.model_dump())
            or ExperimentCreateResponse(experiment_id="exp-degraded", status="draft")
        ),
    )
    monkeypatch.setattr(
        router_mod, "trigger_run",
        lambda *, experiment_id, request, request_id, bq, _: ExperimentRunResponse(
            run_id="run-degraded", status="running"
        ),
    )

    app_module.app.dependency_overrides[get_bq_client] = lambda: object()
    try:
        with TestClient(app_module.app, raise_server_exceptions=False) as client:
            session_id = _walk_a_complete_session(client, "no key here")

            extract = client.post(f"/api/v1/scoping/sessions/{session_id}/extract")
            assert extract.status_code == 200, extract.text
            assert extract.json()["extraction_unavailable"] is True
            assert extract.json()["prefills"] == []

            brief = client.get(f"/api/v1/scoping/sessions/{session_id}/brief")
            assert brief.status_code == 200
            approve = client.post(
                f"/api/v1/scoping/sessions/{session_id}/approve",
                json={"config_hash": brief.json()["config_hash"]},
            )
            assert approve.status_code == 200, approve.text
            dispatch = client.post(f"/api/v1/scoping/sessions/{session_id}/dispatch")
    finally:
        app_module.app.dependency_overrides.clear()

    assert dispatch.status_code == 202, dispatch.text
    assert created, "dispatch did not reach the wizard's create_experiment handler"


# ── FINDING HC-S6-F8 ─────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F8: when insert_gap raises, app/routers/scoping.py "
        "logs and `continue`s, so the gap is dropped from the response as well "
        "as from the table. The user is told nothing about the concept the "
        "platform cannot express — the gap record is the deliverable of the "
        "whole stop-at-the-wall design. Implementation deliberately not "
        "modified."
    ),
)
def test_a_gap_that_fails_to_persist_is_still_reported_to_the_user(backend_root):
    """
    ATTACK: make the capability_gaps insert fail and see what the caller is told.

    Read from source rather than driven, because reaching it needs a live model
    call. The `continue` is unambiguous: the gap never reaches `persisted`, and
    `persisted` is the whole `gaps` field of the response.
    """
    source = (backend_root / "app" / "routers" / "scoping.py").read_text(encoding="utf-8")
    extract_src = next(
        ast.unparse(node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "extract"
    )
    assert "continue" not in extract_src or "failed_gaps" in extract_src, (
        "a capability gap that cannot be written is silently dropped from the "
        "response; the caller cannot tell 'no gaps' from 'the gap write failed'"
    )

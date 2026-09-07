"""
Stage 3 tests — extraction and capability-gap detection.

The extractor is stubbed. What is tested is the contract around it: that a
malformed or over-reaching response is rejected rather than repaired, that a
pre-fill can never become an answer, that the session completes without it, and
that gap detection classifies correctly.

Matt's own example is the fixture:
    "teams with heavier O lines perform better in poor weather"
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.claude_scoping import ClaudeScopingError, _validate
from app.dependencies import get_bq_client
from app.main import app
from app.queries import features as fq
from app.queries import scoping as sq
from app.routers import scoping as router_mod
from app.scoping.gaps import WHY_FEATURE_CATALOG, WHY_FILTER_SCHEMA, detect_gaps, resolve_concept
from app.scoping.schema import load_tree

CATALOG = [
    {"column": "temp", "semantic_name": "temp", "dataset": "curated", "description": "Game-time temperature (°F)"},
    {"column": "wind", "semantic_name": "wind", "dataset": "curated", "description": "Wind speed (mph)"},
    {"column": "roof_dome", "semantic_name": "roof_dome", "dataset": "curated", "description": "1 if dome"},
    {"column": "div_game", "semantic_name": "div_game", "dataset": "curated", "description": "Divisional flag"},
]
FILTERABLE = {"div_game", "week"}


# ── the response contract ────────────────────────────────────────────────────


def _ok(**over):
    base = {"slot_prefills": {}, "unmatched_concepts": [], "requested_slices": []}
    base.update(over)
    return base


def test_valid_response_passes():
    _validate(_ok(), {"target"}, {"temp"})


def test_missing_key_is_rejected():
    with pytest.raises(ClaudeScopingError, match="missing required keys"):
        _validate({"slot_prefills": {}, "unmatched_concepts": []}, {"target"}, {"temp"})


def test_extra_key_is_rejected():
    """A response with unexpected keys is not repaired — it is refused."""
    with pytest.raises(ClaudeScopingError, match="unexpected keys"):
        _validate(_ok(commentary="I think..."), {"target"}, {"temp"})


def test_slot_not_in_the_tree_is_rejected():
    with pytest.raises(ClaudeScopingError, match="not in the tree"):
        _validate(_ok(slot_prefills={"invented_slot": {"value": 1}}), {"target"}, {"temp"})


def test_hallucinated_feature_is_rejected():
    """
    The one hallucination that would be materially harmful: it would arrive
    looking like a real selection the user made.
    """
    bad = _ok(slot_prefills={"features": {"value": [{"dataset": "curated", "column": "ol_avg_weight"}]}})
    with pytest.raises(ClaudeScopingError, match="not in the catalog"):
        _validate(bad, {"features"}, {"temp", "wind"})


def test_real_feature_is_accepted():
    good = _ok(slot_prefills={"features": {"value": [{"dataset": "curated", "column": "temp"}]}})
    _validate(good, {"features"}, {"temp", "wind"})


def test_unmatched_concepts_must_be_strings():
    with pytest.raises(ClaudeScopingError, match="list of strings"):
        _validate(_ok(unmatched_concepts=[{"nope": 1}]), {"target"}, {"temp"})


# ── gap detection ────────────────────────────────────────────────────────────


def test_weather_resolves_and_is_not_a_feature_gap():
    """
    A model reporting weather as unavailable is wrong — temp, wind and roof_dome
    exist. concepts.json corrects it without a second API call.
    """
    assert resolve_concept("poor weather", CATALOG) is not None
    gaps = detect_gaps(["poor weather"], CATALOG, filterable_fields=FILTERABLE)
    assert gaps == []


def test_ol_weight_is_a_feature_gap():
    gaps = detect_gaps(["average offensive line weight"], CATALOG, filterable_fields=FILTERABLE)
    assert len(gaps) == 1
    assert gaps[0]["why_unavailable"] == WHY_FEATURE_CATALOG


def test_weather_as_a_slice_is_a_filter_gap():
    """
    The distinction most hypotheses run into: weather exists as a model input
    and cannot be used to restrict the game universe. Adding a feature is not a
    fix for that, so it is reported as a different kind of gap.
    """
    gaps = detect_gaps([], CATALOG, requested_slices=["poor weather"], filterable_fields=FILTERABLE)
    assert len(gaps) == 1
    assert gaps[0]["why_unavailable"] == WHY_FILTER_SCHEMA
    assert "temp" in gaps[0]["nearest_expressible"]
    assert "GameUniverseFilter" in gaps[0]["suggested_definition"]


def test_a_slice_that_is_already_filterable_is_not_a_gap():
    gaps = detect_gaps([], CATALOG, requested_slices=["divisional games"], filterable_fields=FILTERABLE)
    assert gaps == []


def test_widening_the_filter_removes_the_gap_with_no_code_change():
    """
    The property that makes this survive: gap detection reads the allowed fields
    from the schema. When GameUniverseFilter accepts temp, this stops reporting.
    """
    gaps = detect_gaps([], CATALOG, requested_slices=["poor weather"],
                       filterable_fields=FILTERABLE | {"temp", "wind", "roof_dome"})
    assert gaps == []


def test_matts_hypothesis_produces_exactly_two_gaps():
    """teams with heavier O lines perform better in poor weather"""
    gaps = detect_gaps(
        unmatched_concepts=["average offensive line weight"],
        catalog=CATALOG,
        requested_slices=["poor weather"],
        filterable_fields=FILTERABLE,
    )
    by_kind = {g["why_unavailable"]: g for g in gaps}
    assert set(by_kind) == {WHY_FEATURE_CATALOG, WHY_FILTER_SCHEMA}
    assert "weight" in by_kind[WHY_FEATURE_CATALOG]["requested_concept"]
    assert "weather" in by_kind[WHY_FILTER_SCHEMA]["requested_concept"]


def test_duplicate_concepts_produce_one_gap():
    gaps = detect_gaps(["ol weight", "OL Weight", "ol weight"], CATALOG, filterable_fields=FILTERABLE)
    assert len(gaps) == 1


def test_every_concepts_json_feature_exists_in_the_live_catalog():
    """A stale alias entry must fail here, not resolve to nothing in production."""
    from app.scoping.gaps import load_concepts
    live = {f["semantic_name"] for f in fq._CATALOG}
    for entry in load_concepts():
        for feature in entry["features"]:
            assert feature in live, f"concepts.json references missing feature {feature!r}"


# ── the endpoint ─────────────────────────────────────────────────────────────


class Store:
    def __init__(self):
        self.rows, self.gaps = {}, []

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

    def insert_gap(self, _c, **kw):
        self.gaps.append(kw)


@pytest.fixture
def store(monkeypatch):
    s = Store()
    for fn in ("create_session", "get_session", "update_answers", "insert_gap"):
        monkeypatch.setattr(sq, fn, getattr(s, fn))
    monkeypatch.setattr(fq, "list_features", lambda _c: [
        {"semantic_name": c["column"], "dataset": "curated", "description": c["description"]}
        for c in CATALOG
    ])
    return s


@pytest.fixture
def client(store):
    app.dependency_overrides[get_bq_client] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _session(client, text="teams with heavier O lines perform better in poor weather"):
    return client.post("/api/v1/scoping/sessions", json={"hypothesis_text": text}).json()["session_id"]


def test_extract_returns_unconfirmed_prefills(client, monkeypatch):
    monkeypatch.setattr(router_mod, "extract_slots", lambda **kw: {
        "slot_prefills": {"target": {"value": "ats_cover", "confidence": 0.9,
                                     "evidence_quote": "perform better"}},
        "unmatched_concepts": [], "requested_slices": [],
    })
    r = client.post(f"/api/v1/scoping/sessions/{_session(client)}/extract")
    assert r.status_code == 200, r.text
    prefill = r.json()["prefills"][0]
    assert prefill["confirmed"] is False
    assert prefill["evidence_quote"] == "perform better"


def test_a_prefill_does_not_answer_the_question(client, monkeypatch):
    """
    The highest-consequence failure in the design: a slot filled and never
    questioned. Extraction must not advance the session by even one question.
    """
    sid = _session(client)
    before = client.get(f"/api/v1/scoping/sessions/{sid}").json()

    monkeypatch.setattr(router_mod, "extract_slots", lambda **kw: {
        "slot_prefills": {"target": {"value": "ats_cover", "confidence": 1.0, "evidence_quote": "x"}},
        "unmatched_concepts": [], "requested_slices": [],
    })
    client.post(f"/api/v1/scoping/sessions/{sid}/extract")

    after = client.get(f"/api/v1/scoping/sessions/{sid}").json()
    assert after["answers"] == before["answers"] == {}
    assert after["next_question"]["slot_id"] == before["next_question"]["slot_id"]
    assert "target" not in after["answers"]


def test_extract_records_gaps_for_matts_hypothesis(client, monkeypatch, store):
    monkeypatch.setattr(router_mod, "extract_slots", lambda **kw: {
        "slot_prefills": {},
        "unmatched_concepts": ["average offensive line weight"],
        "requested_slices": ["poor weather"],
    })
    body = client.post(f"/api/v1/scoping/sessions/{_session(client)}/extract").json()

    kinds = {g["why_unavailable"] for g in body["gaps"]}
    assert kinds == {WHY_FEATURE_CATALOG, WHY_FILTER_SCHEMA}
    assert len(store.gaps) == 2, "gaps must be persisted, not just returned"
    assert all(g["gap_id"] for g in body["gaps"])


def test_extraction_unavailable_is_not_an_error(client, monkeypatch):
    """
    With no API key the endpoint reports unavailability and the session carries
    on. Stage 3 is additive; it cannot block a run.
    """
    def boom(**kw):
        raise ClaudeScopingError("ANTHROPIC_API_KEY is not configured")
    monkeypatch.setattr(router_mod, "extract_slots", boom)

    r = client.post(f"/api/v1/scoping/sessions/{_session(client)}/extract")
    assert r.status_code == 200
    assert r.json()["extraction_unavailable"] is True
    assert r.json()["prefills"] == []


def test_session_still_completes_with_extraction_unavailable(client, monkeypatch):
    def boom(**kw):
        raise ClaudeScopingError("no key")
    monkeypatch.setattr(router_mod, "extract_slots", boom)

    sid = _session(client)
    client.post(f"/api/v1/scoping/sessions/{sid}/extract")

    tree = load_tree()
    while True:
        state = client.get(f"/api/v1/scoping/sessions/{sid}").json()
        q = state["next_question"]
        if q is None:
            break
        value = q["default"]
        if value is None:
            if q["type"] == "text":
                value = "x"
            elif q["type"] == "multi_select":
                value = [{"dataset": "curated", "column": "temp", "semantic_name": "temp"}]
        client.post(f"/api/v1/scoping/sessions/{sid}/answers",
                    json={"slot_id": q["slot_id"], "value": value})

    assert client.get(f"/api/v1/scoping/sessions/{sid}").json()["status"] == "assembled"
    assert len(tree.slots) > 0

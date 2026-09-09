"""
FINDING HC-S6-F9 — the approval hash has to survive storage.

`dispatch` recomputes the hash from `slot_answers` read back OUT of BigQuery and
compares it to the approval. So the property that matters is not that the hash
is stable in a Python process — every existing test checked that — but that it
is stable across a storage round-trip.

It was not. BigQuery's JSON type returns `2.0` as `2`, and hashing.py
deliberately treated int and float as different configs. Any config holding a
whole-number float therefore could not match its own approval: it failed closed,
refused with `approval_mismatch`, and wedged the session permanently with no way
forward. The distinction was unenforceable through the storage layer and has
been removed.

TWO TESTS, AND WHY BOTH
-----------------------
`test_the_hash_survives_a_simulated_round_trip` runs everywhere, but it round-
trips through a MODEL of BigQuery's behaviour — and a model of the world written
by the same author is what let this class of bug through five stages. It is here
because it runs in CI, not because it is evidence.

`test_the_hash_survives_a_real_round_trip` is the evidence. It needs ADC and
skips loudly without it, naming what was not verified rather than reporting a
pass. Run it with:

    gcloud auth application-default login
    cd 03-BACKEND-API && pytest tests/test_scoping_hash_roundtrip.py -v
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.scoping.hashing import approval_hash, canonical_json, config_hash

TAG = "hcs6-backend-roundtrip"


# ── the property, in a process ───────────────────────────────────────────────


def _as_bigquery_returns(value):
    """
    What BigQuery's JSON type gives back, as OBSERVED by TESTING-QA against the
    live tables on 2026-09-08 (HC-S6-FINDINGS.md, F9): a whole-number float
    comes back as an integer.

    This is a model, not the thing. The live test below is the thing.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _as_bigquery_returns(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_bigquery_returns(v) for v in value]
    return value


CONFIG_WITH_WHOLE_FLOATS = {
    "name": "Ölïne 大きい 🏈",
    "target": "ats_cover",
    "features": [{"dataset": "curated", "column": "home_ol_sack_rate", "semantic_name": None}],
    "evaluation": {"metric": "ats_hit_rate", "success_threshold": 0.53, "min_sample": 500.0},
    "methodology": {"type": "walk_forward", "start_season": 2015.0, "end_season": 2025,
                    "train_seasons": 4.0, "test_seasons": 1, "game_universe": None},
    "model": {"type": "xgboost", "hyperparams": {"max_depth": 6.0, "eta": 0.05}},
}


def test_the_hash_survives_a_simulated_round_trip():
    stored = json.loads(json.dumps(CONFIG_WITH_WHOLE_FLOATS))
    returned = _as_bigquery_returns(stored)

    assert returned["evaluation"]["min_sample"] == 500
    assert isinstance(returned["evaluation"]["min_sample"], int), "the model is wrong"
    assert config_hash(returned) == config_hash(CONFIG_WITH_WHOLE_FLOATS), (
        "a config with a whole-number float cannot match its own approval after "
        "storage — the session wedges with approval_mismatch and no way out"
    )


def test_canonicalisation_is_idempotent():
    """canonical_json(x) == canonical_json(round_trip(x)), which is the property."""
    once = canonical_json(CONFIG_WITH_WHOLE_FLOATS)
    twice = canonical_json(json.loads(once))
    assert once == twice


def test_the_approval_hash_survives_the_round_trip_too():
    """The stored approval covers the record-only answers, so it round-trips too."""
    record_only = {"mechanism": "market lag", "falsifier": "below 50% ATS in every fold"}
    returned = _as_bigquery_returns(json.loads(json.dumps(CONFIG_WITH_WHOLE_FLOATS)))
    assert approval_hash(returned, record_only) == \
           approval_hash(CONFIG_WITH_WHOLE_FLOATS, record_only)


def test_a_fractional_float_is_untouched_by_storage_or_by_us():
    assert '"success_threshold":0.53' in canonical_json(CONFIG_WITH_WHOLE_FLOATS)


# ── the property, against the real thing ─────────────────────────────────────


def _credentials_available() -> tuple[bool, str]:
    try:
        import google.auth
        google.auth.default()
    except Exception as exc:
        return False, str(exc).splitlines()[0][:160]
    return True, ""


@pytest.mark.integration
@pytest.mark.live
def test_the_hash_survives_a_real_round_trip():
    """
    Write a config holding a whole-number float to platform.scoping_sessions,
    read it back through the real query layer, rehash, and compare.

    No unit test could have caught F9 — the normalisation happens inside
    BigQuery. Removes its own row afterwards and proves the removal.
    """
    ok, why = _credentials_available()
    if not ok:
        pytest.skip(
            "NOT VERIFIED: the hash was not round-tripped through real BigQuery "
            f"in this environment ({why}). This is the only test that can prove "
            "F9 is closed; storage is deliberately not faked here. Run it with "
            "ADC: gcloud auth application-default login."
        )

    from google.cloud import bigquery
    from app.queries import scoping as sq

    client = bigquery.Client()
    session_id = str(uuid.uuid4())
    answers = {"name": f"{TAG}", "min_sample": 500.0, "success_threshold": 0.53}

    try:
        sq.create_session(client, session_id, f"{TAG} float round trip")
        before = config_hash(CONFIG_WITH_WHOLE_FLOATS)
        sq.update_answers(client, session_id, answers, CONFIG_WITH_WHOLE_FLOATS,
                          before, "assembled")

        stored = sq.get_session(client, session_id)
        assert config_hash(stored["config"]) == before, (
            "the config that came back out of BigQuery does not hash to the "
            "value that went in — a legitimately approved experiment can never "
            "be dispatched"
        )
        assert config_hash(stored["slot_answers"]) == config_hash(answers)

        # And the guarantee end to end: approve the stored hash, then recompute
        # from storage the way dispatch does.
        assert sq.set_approved_hash(client, session_id, before) is True
        approved = sq.get_session(client, session_id)
        assert approved["approved_hash"] == config_hash(approved["config"])
    finally:
        client.query(
            f"DELETE FROM `{sq.SESSIONS}` WHERE session_id = @sid",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("sid", "STRING", session_id)]),
        ).result()
        left = list(client.query(
            f"SELECT COUNT(*) AS n FROM `{sq.SESSIONS}` WHERE session_id = @sid",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("sid", "STRING", session_id)]),
        ).result())
        assert left[0]["n"] == 0, "this test left a row behind in a production table"

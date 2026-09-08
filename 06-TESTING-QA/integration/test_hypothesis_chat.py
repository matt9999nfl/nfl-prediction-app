"""
Hypothesis Chat against REAL BigQuery — HC-S6 requirement A.

Stages 0-5 have never run against live storage: every test to date used mocks
or an in-memory stand-in. This module is the one that closes that gap, and it
is the only module in this suite permitted to claim it.

IT IS CURRENTLY SKIPPED. This environment has no gcloud, no ADC, no key file
and no GOOGLE_APPLICATION_CREDENTIALS, so `bigquery.Client()` cannot
authenticate. Per the HC-S6 brief's kill-switch, storage is NOT faked to get a
green run — that is the exact gap this stage exists to close, and a stand-in
here would reproduce the very problem that let FINDING HC-S6-F1 through. See
00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md, question HC-S6-Q1.

WHAT THIS MODULE MAY AND MAY NOT WRITE
--------------------------------------
May:     platform.scoping_sessions, platform.capability_gaps
May, with cleanup: platform.experiment_configs (create_experiment writes here)
Must not: experiments.*, curated.*, raw_*

`dispatch` is NOT driven end to end here, and that is deliberate rather than an
omission. app/routers/experiments.py::trigger_run calls
queries/experiments.py::trigger_experiment_runner, which fires the production
Cloud Run Job `nfl-experiment-runner`; that job writes experiments.backtest_runs
and experiments.backtest_predictions. A test that dispatches for real therefore
writes to experiments.* through one level of indirection, which is a kill-switch
condition, and it cannot clean up after itself. Escalated as HC-S6-Q2; the
dispatch tests below stop at the guarantee boundary (the 409s) and the one that
would complete a run is marked with the escalation.

CLEANUP
-------
The root conftest's `cleanup_test_rows` deletes `WHERE experiment_id LIKE
'test_%'`, which cannot match anything this flow creates: create_experiment
assigns `str(uuid.uuid4())`. It also does not touch platform.scoping_sessions
or platform.capability_gaps at all. So this module tracks every id it creates
and removes them itself, then PROVES the tables are clean with a post-run count
rather than assuming it.
"""
from __future__ import annotations

import os
import uuid

import pytest

PROJECT = "nfl-model-471509"
SESSIONS = f"{PROJECT}.platform.scoping_sessions"
GAPS = f"{PROJECT}.platform.capability_gaps"
CONFIGS = f"{PROJECT}.platform.experiment_configs"

# Marker written into every row this module creates, so cleanup is exact and a
# leaked row is identifiable by eye in the console.
TAG = "hcs6-testing-qa"


def _credentials_available() -> tuple[bool, str]:
    try:
        import google.auth
    except Exception as exc:  # pragma: no cover
        return False, f"google.auth not importable: {exc}"
    try:
        google.auth.default()
    except Exception as exc:
        return False, str(exc)
    return True, ""


_OK, _WHY = _credentials_available()
if not _OK:
    pytest.skip(
        "HC-S6 requirement A is UNMET, not passing. No GCP credentials in this "
        f"environment ({_WHY.splitlines()[0][:160]}). Storage is deliberately "
        "not faked — see the module docstring and "
        "00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md HC-S6-Q1.",
        allow_module_level=True,
    )

from google.cloud import bigquery  # noqa: E402  (only reachable with credentials)

pytestmark = [pytest.mark.integration, pytest.mark.live]


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def created_ids():
    """Ids this test created, by table. Emptied by `scoping_cleanup`."""
    return {"sessions": [], "gaps": [], "experiments": []}


@pytest.fixture
def scoping_cleanup(bq_client, created_ids):
    """
    Removes exactly what the test created, then asserts it is gone.

    Additive to the root `cleanup_test_rows`, which cannot see these rows.
    """
    yield created_ids

    for table, column, ids in (
        (SESSIONS, "session_id", created_ids["sessions"]),
        (GAPS, "gap_id", created_ids["gaps"]),
        (CONFIGS, "experiment_id", created_ids["experiments"]),
    ):
        if not ids:
            continue
        bq_client.query(
            f"DELETE FROM `{table}` WHERE {column} IN UNNEST(@ids)",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
            ),
        ).result()

    # Proof, not assumption.
    for table, column, ids in (
        (SESSIONS, "session_id", created_ids["sessions"]),
        (GAPS, "gap_id", created_ids["gaps"]),
        (CONFIGS, "experiment_id", created_ids["experiments"]),
    ):
        if not ids:
            continue
        rows = list(
            bq_client.query(
                f"SELECT COUNT(*) AS n FROM `{table}` WHERE {column} IN UNNEST(@ids)",
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
                ),
            ).result()
        )
        assert rows[0]["n"] == 0, f"{rows[0]['n']} test row(s) left behind in {table}"


@pytest.fixture
def scoping_queries():
    """The real app/queries/scoping.py, talking to the real tables."""
    backend = os.getenv("NFL_BACKEND_ROOT")
    if backend:
        import sys
        if backend not in sys.path:
            sys.path.insert(0, backend)
    try:
        from app.queries import scoping as sq
        from app.scoping.assemble import assemble, record_only_answers
        from app.scoping.hashing import config_hash
        from app.scoping.render import render
        from app.scoping.schema import load_tree
    except ImportError as exc:
        pytest.skip(f"backend not importable ({exc}); set NFL_BACKEND_ROOT")
    return {
        "sq": sq, "assemble": assemble, "record_only": record_only_answers,
        "config_hash": config_hash, "render": render, "load_tree": load_tree,
    }


def _answers(tree, features):
    answers = {slot.id: slot.default for slot in tree.slots}
    answers.update(
        {
            "features": features,
            "mechanism": f"{TAG} — OL pass protection is undervalued",
            "falsifier": "below 50% ATS in every fold",
            "prior_attempts": None,
            "name": f"{TAG} Ölïne 大きい 🏈",
        }
    )
    return answers


# ── A. the full round trip ───────────────────────────────────────────────────


def test_a_session_round_trips_through_real_bigquery(
    bq_client, scoping_queries, scoping_cleanup
):
    """
    Create, answer every slot, assemble, hash, approve — against the real
    platform.scoping_sessions — and read every field back.

    The JSON columns are the point: BigQuery JSON does not round-trip the way a
    dict in a Python process does, and nothing has ever checked it here.
    """
    sq = scoping_queries["sq"]
    tree = scoping_queries["load_tree"]()

    session_id = str(uuid.uuid4())
    scoping_cleanup["sessions"].append(session_id)

    sq.create_session(bq_client, session_id, f"{TAG} heavier O-lines cover in bad weather")
    row = sq.get_session(bq_client, session_id)
    assert row is not None, "the row we just inserted cannot be read back"
    assert row["status"] == "scoping"
    assert row["slot_answers"] == {}
    assert row["config"] is None
    assert row["approved_hash"] is None

    features = [
        {"dataset": "curated", "column": "home_ol_sack_rate", "semantic_name": "home_ol_sack_rate"},
        {"dataset": "curated", "column": "away_ol_sack_rate", "semantic_name": "away_ol_sack_rate"},
    ]
    answers = _answers(tree, features)
    payload = scoping_queries["assemble"](tree, answers)
    chash = scoping_queries["config_hash"](payload)

    sq.update_answers(bq_client, session_id, answers, payload, chash, "assembled")
    stored = sq.get_session(bq_client, session_id)

    assert stored["config_hash"] == chash
    assert stored["status"] == "assembled"
    assert scoping_queries["config_hash"](stored["config"]) == chash, (
        "the config that came back out of BigQuery does not hash to the value "
        "that went in — the approval guarantee does not survive storage"
    )

    sq.set_approved_hash(bq_client, session_id, chash)
    approved = sq.get_session(bq_client, session_id)
    assert approved["approved_hash"] == chash
    assert approved["status"] == "approved"


def test_json_columns_round_trip_nested_arrays_and_explicit_nulls(
    bq_client, scoping_queries, scoping_cleanup
):
    """
    Required by the brief: nested arrays AND explicit nulls, because a JSON
    null collapsing to SQL NULL would be silent.

    An explicit null inside slot_answers is not decoration — an optional slot
    answered "no thanks" is stored as null, and `next_question` decides what to
    ask by membership (`slot.id not in answers`). If a null key were dropped in
    storage, a reloaded session would silently re-ask a question the user had
    already declined, and the config assembled from it could differ.
    """
    sq = scoping_queries["sq"]
    session_id = str(uuid.uuid4())
    scoping_cleanup["sessions"].append(session_id)

    sq.create_session(bq_client, session_id, f"{TAG} json round trip")

    answers = {
        "game_universe": None,               # explicit null
        "prior_attempts": None,              # explicit null
        "hyperparams": {},                   # empty object
        "features": [                        # nested array of objects
            {"dataset": "curated", "column": "home_ol_sack_rate", "semantic_name": None},
            {"dataset": "curated", "column": "away_ol_sack_rate", "semantic_name": "away"},
        ],
        "name": "unicode Ölïne 大きい 🏈",
        "success_threshold": 0.53,
        "min_sample": 500,
    }
    config = {"nested": {"array": [1, 2.0, None, "3"], "null": None}, "empty": {}}

    sq.update_answers(bq_client, session_id, answers, config, "x" * 64, "scoping")
    stored = sq.get_session(bq_client, session_id)

    assert "game_universe" in stored["slot_answers"], (
        "an explicit JSON null was lost in storage; a reloaded session would "
        "re-ask a question the user already declined"
    )
    assert stored["slot_answers"]["game_universe"] is None
    assert stored["slot_answers"]["prior_attempts"] is None
    assert stored["slot_answers"]["hyperparams"] == {}
    assert stored["slot_answers"]["features"] == answers["features"]
    assert stored["slot_answers"]["name"] == answers["name"], "unicode did not survive"
    assert stored["config"] == config, f"config changed in storage: {stored['config']!r}"
    # 2.0 must not come back as 2 — int and float hash differently by design.
    assert isinstance(stored["config"]["nested"]["array"][1], float)


# ── B. the approval guarantee, against real storage ──────────────────────────


def test_attack_answer_after_approval_leaves_the_stored_approval_behind(
    bq_client, scoping_queries, scoping_cleanup
):
    """
    ATTACK, and the reason this module has to exist.

    FINDING HC-S6-F1: sq.update_answers does not clear approved_hash. The
    router sets it to None on the response object only. The implementation's
    own test passes because its in-memory Store DOES clear it.

    This test asserts what the router's comment claims, so it is expected to
    FAIL against real BigQuery. That failure is the deliverable.
    """
    sq = scoping_queries["sq"]
    tree = scoping_queries["load_tree"]()
    session_id = str(uuid.uuid4())
    scoping_cleanup["sessions"].append(session_id)

    features = [{"dataset": "curated", "column": "home_ol_sack_rate",
                 "semantic_name": "home_ol_sack_rate"}]
    answers = _answers(tree, features)
    payload = scoping_queries["assemble"](tree, answers)
    chash = scoping_queries["config_hash"](payload)

    sq.create_session(bq_client, session_id, f"{TAG} approval attack")
    sq.update_answers(bq_client, session_id, answers, payload, chash, "assembled")
    sq.set_approved_hash(bq_client, session_id, chash)

    # Now change one answer, exactly as POST /answers does.
    changed = dict(answers)
    changed["falsifier"] = "I will keep this hypothesis whatever happens"
    new_payload = scoping_queries["assemble"](tree, changed)
    sq.update_answers(
        bq_client, session_id, changed, new_payload,
        scoping_queries["config_hash"](new_payload), "assembled",
    )

    after = sq.get_session(bq_client, session_id)
    assert after["approved_hash"] is None, (
        "FINDING HC-S6-F1: the approval survived an answer change in storage. "
        f"approved_hash is still {after['approved_hash']!r}. dispatch() compares "
        "against this value, so a brief that was never approved can be "
        "dispatched whenever the changed answer leaves the config hash intact "
        "— which is every record-only slot: mechanism, falsifier, prior_attempts."
    )


def test_attack_record_only_change_after_approval_still_dispatches(
    bq_client, scoping_queries, scoping_cleanup
):
    """
    ATTACK: approve, rewrite the falsifier, and see whether the dispatch guard
    still holds.

    The two halves of FINDING HC-S6-F2 combined: the hash covers the config
    payload only, and the stored approval is not cleared. So the guard sees a
    matching hash and lets the run through against a document the user never
    approved.
    """
    sq = scoping_queries["sq"]
    tree = scoping_queries["load_tree"]()
    session_id = str(uuid.uuid4())
    scoping_cleanup["sessions"].append(session_id)

    features = [{"dataset": "curated", "column": "home_ol_sack_rate",
                 "semantic_name": "home_ol_sack_rate"}]
    approved_answers = _answers(tree, features)
    approved_payload = scoping_queries["assemble"](tree, approved_answers)
    approved_hash = scoping_queries["config_hash"](approved_payload)

    sq.create_session(bq_client, session_id, f"{TAG} record-only drift")
    sq.update_answers(bq_client, session_id, approved_answers, approved_payload,
                      approved_hash, "assembled")
    sq.set_approved_hash(bq_client, session_id, approved_hash)

    rewritten = dict(approved_answers)
    rewritten["falsifier"] = "nothing would change my mind"
    rewritten_payload = scoping_queries["assemble"](tree, rewritten)
    sq.update_answers(bq_client, session_id, rewritten, rewritten_payload,
                      scoping_queries["config_hash"](rewritten_payload), "assembled")

    row = sq.get_session(bq_client, session_id)
    recomputed = scoping_queries["config_hash"](
        scoping_queries["assemble"](tree, row["slot_answers"])
    )
    would_dispatch = bool(row["approved_hash"]) and row["approved_hash"] == recomputed

    kwargs = dict(hypothesis_text=f"{TAG} record-only drift", tree=tree)
    approved_brief = scoping_queries["render"](
        approved_payload,
        record_only=scoping_queries["record_only"](tree, approved_answers), **kwargs)
    current_brief = scoping_queries["render"](
        rewritten_payload,
        record_only=scoping_queries["record_only"](tree, rewritten), **kwargs)

    assert not (would_dispatch and approved_brief != current_brief), (
        "FINDING HC-S6-F2: dispatch would proceed against a brief that differs "
        "from the one approved. The falsifier changed; the hash did not."
    )


def test_attack_replay_a_stale_hash_from_a_different_session(
    bq_client, scoping_queries, scoping_cleanup
):
    """
    ATTACK: take the approved hash from session A and try to authorise session
    B with it. Expected to HOLD — approve recomputes from B's own answers.
    """
    sq = scoping_queries["sq"]
    tree = scoping_queries["load_tree"]()
    features = [{"dataset": "curated", "column": "home_ol_sack_rate",
                 "semantic_name": "home_ol_sack_rate"}]

    session_a, session_b = str(uuid.uuid4()), str(uuid.uuid4())
    scoping_cleanup["sessions"] += [session_a, session_b]

    answers_a = _answers(tree, features)
    hash_a = scoping_queries["config_hash"](scoping_queries["assemble"](tree, answers_a))

    answers_b = dict(answers_a)
    answers_b["min_sample"] = 250        # a materially different experiment
    payload_b = scoping_queries["assemble"](tree, answers_b)
    hash_b = scoping_queries["config_hash"](payload_b)

    assert hash_a != hash_b, "fixture is wrong — the two sessions must differ"

    sq.create_session(bq_client, session_b, f"{TAG} stale hash replay")
    sq.update_answers(bq_client, session_b, answers_b, payload_b, hash_b, "assembled")
    # A replayed approval would write hash_a here; the router refuses before
    # this point, so what is asserted is that the store never holds a hash that
    # does not match its own answers.
    stored = sq.get_session(bq_client, session_b)
    recomputed = scoping_queries["config_hash"](
        scoping_queries["assemble"](tree, stored["slot_answers"])
    )
    assert stored["config_hash"] == recomputed != hash_a


def test_attack_concurrent_answer_and_approve(bq_client, scoping_queries, scoping_cleanup):
    """
    ATTACK: interleave an answer write and an approve write on the same
    session and see which one lands last.

    Both endpoints read, decide, then write, with no condition on the UPDATE
    and no transaction. approve's UPDATE sets approved_hash and status without
    checking that the answers are still the ones it hashed.
    """
    import concurrent.futures

    sq = scoping_queries["sq"]
    tree = scoping_queries["load_tree"]()
    features = [{"dataset": "curated", "column": "home_ol_sack_rate",
                 "semantic_name": "home_ol_sack_rate"}]
    session_id = str(uuid.uuid4())
    scoping_cleanup["sessions"].append(session_id)

    answers = _answers(tree, features)
    payload = scoping_queries["assemble"](tree, answers)
    chash = scoping_queries["config_hash"](payload)

    sq.create_session(bq_client, session_id, f"{TAG} concurrency")
    sq.update_answers(bq_client, session_id, answers, payload, chash, "assembled")

    changed = dict(answers)
    changed["min_sample"] = 999
    changed_payload = scoping_queries["assemble"](tree, changed)
    changed_hash = scoping_queries["config_hash"](changed_payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(sq.update_answers, bq_client, session_id, changed,
                        changed_payload, changed_hash, "assembled"),
            pool.submit(sq.set_approved_hash, bq_client, session_id, chash),
        ]
        for future in futures:
            future.result()

    row = sq.get_session(bq_client, session_id)
    recomputed = scoping_queries["config_hash"](
        scoping_queries["assemble"](tree, row["slot_answers"])
    )
    if row["approved_hash"]:
        assert row["approved_hash"] == recomputed, (
            "a race left an approval attached to answers it was not computed "
            f"from: approved={row['approved_hash'][:12]}, "
            f"answers hash to {recomputed[:12]}. dispatch compares these two, "
            "so this specific state is refused — but the session is wedged "
            "until the user re-approves, with no message saying why."
        )


@pytest.mark.skip(
    reason=(
        "ESCALATED — HC-S6-Q2. Completing a dispatch calls trigger_run, which "
        "fires the production Cloud Run Job nfl-experiment-runner; that job "
        "writes experiments.backtest_runs and experiments.backtest_predictions. "
        "The HC-S6 brief's kill-switch forbids writing to experiments.*, and "
        "those rows cannot be cleaned up from here. Needs a ruling: a runner "
        "no-op switch, a scratch dataset, or explicit permission. See "
        "00-PROJECT-LEAD/HYPOTHESIS-CHAT-QUESTIONS.md."
    )
)
def test_a_full_session_dispatches_to_a_real_experiment_config_row():
    """Requirement A's dispatch half. Written, not run. See the skip reason."""


# ── the post-run proof ───────────────────────────────────────────────────────


def test_the_live_tables_hold_no_rows_from_this_suite(bq_client):
    """
    Runs last by name ordering intent, and is the acceptance criterion "all
    test rows removed afterwards — verified by a post-run count, not assumed".

    Counts anything carrying this suite's tag anywhere in the two scoping
    tables, independently of what any individual test tracked.
    """
    leaked = []
    rows = list(
        bq_client.query(
            f"""
            SELECT COUNT(*) AS n FROM `{SESSIONS}`
            WHERE hypothesis_text LIKE @tag
               OR TO_JSON_STRING(slot_answers) LIKE @tag
            """,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("tag", "STRING", f"%{TAG}%")]
            ),
        ).result()
    )
    if rows[0]["n"]:
        leaked.append(f"{rows[0]['n']} row(s) in {SESSIONS}")

    rows = list(
        bq_client.query(
            f"SELECT COUNT(*) AS n FROM `{GAPS}` WHERE requested_concept LIKE @tag",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("tag", "STRING", f"%{TAG}%")]
            ),
        ).result()
    )
    if rows[0]["n"]:
        leaked.append(f"{rows[0]['n']} row(s) in {GAPS}")

    assert not leaked, "this suite left rows in production tables: " + "; ".join(leaked)

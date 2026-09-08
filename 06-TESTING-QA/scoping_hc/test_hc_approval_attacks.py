"""
Requirement B — the approval guarantee, attacked rather than confirmed.

Every test here is named for what it ATTEMPTS, not for what it expects.

Split of work: the attacks below are the ones that can be settled without
storage — by reading the DML the session store actually emits, and by driving
the pure assemble/hash layer. The attacks that need a live session
(concurrency, dispatch-twice races, replay across persisted sessions) are in
integration/test_hypothesis_chat.py, which requires real BigQuery and is
skipped without it rather than run against a stand-in.

That split is not a convenience. The single most important thing found here is
that the in-memory stand-in used by the implementation's own tests
(03-BACKEND-API/tests/test_scoping_api.py::Store) does something the real SQL
does not, and the test that guards the approval guarantee passes because of it.
"""
from __future__ import annotations

import ast
import re

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def queries_src(backend_root):
    return (backend_root / "app" / "queries" / "scoping.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def router_src(backend_root):
    return (backend_root / "app" / "routers" / "scoping.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def impl_api_test_src(backend_root):
    return (backend_root / "tests" / "test_scoping_api.py").read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(f"function {name!r} not found")


def _sql_strings(function_source: str) -> str:
    return "\n".join(
        node.value
        for node in ast.walk(ast.parse(function_source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


# ── FINDING HC-S6-F1 ─────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F1: sq.update_answers never clears approved_hash. The "
        "router sets approved_hash=None on the in-memory row it returns to the "
        "caller, so the RESPONSE says the approval was cleared while the stored "
        "row still holds it. The implementation's own test passes because the "
        "in-memory Store clears the field and the real UPDATE does not. "
        "Implementation deliberately not modified."
    ),
)
def test_attack_answer_after_approval_leaves_a_stored_approval_behind(queries_src):
    """
    ATTACK: answer a slot after approving, and see whether the approval that
    was given for the previous brief is still sitting in the database.

    app/routers/scoping.py L163-165 states the intent plainly: "An answer that
    changes the config necessarily changes the hash, which invalidates any
    prior approval — approved_hash is cleared so approval must be given again."
    The UPDATE it issues sets slot_answers, config, config_hash, status and
    updated_at. It does not mention approved_hash.
    """
    sql = _sql_strings(_function_source(queries_src, "update_answers"))
    set_clause = sql[sql.upper().find("SET"):] if "SET" in sql.upper() else sql
    assert "approved_hash" in set_clause, (
        "update_answers does not clear approved_hash. The stored approval "
        "survives an answer change; only the response body pretends otherwise."
    )


def test_the_in_memory_stand_in_clears_what_the_real_sql_does_not(
    queries_src, impl_api_test_src
):
    """
    Why F1 was invisible until now, stated as an assertion.

    This test PASSES, and its passing is the finding: the stand-in and the
    real store disagree on the one field the approval guarantee rests on.
    Every existing approval test runs against the stand-in.
    """
    store_update = _function_source(impl_api_test_src, "update_answers")
    real_update = _sql_strings(_function_source(queries_src, "update_answers"))

    assert "approved_hash" in store_update, (
        "the stand-in no longer clears approved_hash — re-read this finding"
    )
    assert "approved_hash" not in real_update, (
        "the real UPDATE now touches approved_hash — F1 may be fixed"
    )


# ── FINDING HC-S6-F7 ─────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING HC-S6-F7: approve() has no already-dispatched guard and "
        "set_approved_hash resets status to 'approved'. dispatch() refuses a "
        "second run by checking status == 'dispatched', so approving again "
        "after a dispatch clears that guard and a second experiment and a "
        "second Cloud Run job can be created from one session. "
        "Implementation deliberately not modified."
    ),
)
def test_attack_reapprove_after_dispatch_to_clear_the_already_dispatched_guard(
    router_src, queries_src
):
    """
    ATTACK: dispatch, then approve again, then dispatch again.

    dispatch() and answer_slot() both refuse when the loaded row says
    'dispatched'. approve() does not check status at all, and the UPDATE it
    issues sets status = 'approved' unconditionally — so the guard on the only
    two endpoints that have one can be reset by calling a third that does not.

    Consequence: two experiments, two runner jobs, and mark_dispatched
    overwrites session.experiment_id so the first one is orphaned from the
    session that produced it.
    """
    approve_src = _function_source(router_src, "approve")
    assert "already_dispatched" in approve_src or "dispatched" in approve_src, (
        "approve() does not check whether the session has already been "
        "dispatched, and set_approved_hash resets status to 'approved', which "
        "re-opens dispatch()'s only guard against a second run."
    )


def test_reapproving_resets_the_status_that_guards_dispatch(queries_src):
    """
    The second half of F7, asserted separately so the mechanism is on record.

    This test PASSES; it documents the behaviour that makes F7 reachable.
    """
    sql = _sql_strings(_function_source(queries_src, "set_approved_hash"))
    assert "status = 'approved'" in sql, "set_approved_hash no longer sets status"
    assert "WHERE session_id" in sql and "status" not in sql.split("WHERE")[1], (
        "set_approved_hash now filters on status — F7 may be closed"
    )


# ── attacks the guarantee survives ───────────────────────────────────────────


def test_attack_500_vs_500_point_0_to_collide_two_configs(scoping_api):
    """
    ATTACK: change min_sample from 500 to 500.0 and hope the canonicaliser
    normalises the difference away, so a config approved as one is dispatched
    as the other.

    HELD. json.dumps keeps int and float distinct, so the hash moves and
    dispatch's recomputation refuses.
    """
    config_hash = scoping_api["hashing"].config_hash
    base = {"evaluation": {"min_sample": 500}}
    floated = {"evaluation": {"min_sample": 500.0}}
    assert config_hash(base) != config_hash(floated)


def test_attack_unicode_normalisation_to_collide_two_names(scoping_api):
    """
    ATTACK: two experiment names that look identical but are different byte
    sequences (composed vs decomposed accents). If the canonicaliser folded
    them, a brief could be approved under one name and run under another.

    HELD. ensure_ascii=False preserves the bytes as given and the hashes differ.
    """
    config_hash = scoping_api["hashing"].config_hash
    composed = {"name": "café experiment"}      # é as one code point
    decomposed = {"name": "café experiment"}   # e + combining acute
    assert composed["name"] != decomposed["name"]
    assert config_hash(composed) != config_hash(decomposed)


def test_attack_reorder_features_to_change_the_run_without_changing_the_hash(scoping_api):
    """
    ATTACK: the brief sorts features for display. If the hash were taken over
    the sorted view rather than the payload, reordering the answer would change
    what runs while the brief and hash stayed still.

    HELD. The hash is taken over the payload, so a reorder moves it — the
    approval is refused rather than silently honouring a different list.
    """
    config_hash = scoping_api["hashing"].config_hash
    a = {"features": [{"dataset": "curated", "column": "b"},
                      {"dataset": "curated", "column": "a"}]}
    b = {"features": [{"dataset": "curated", "column": "a"},
                      {"dataset": "curated", "column": "b"}]}
    assert config_hash(a) != config_hash(b), (
        "feature order does not move the hash; check that render() and dispatch "
        "agree on which order runs"
    )


def test_attack_approve_a_hash_the_client_computed_itself(router_src):
    """
    ATTACK: send an approve body carrying a hash the client made up, hoping the
    server stores what it is given.

    HELD. approve() recomputes the hash from the stored answers and compares;
    the value written is the server's `actual`, never the body's.
    """
    approve_src = _function_source(router_src, "approve")
    assert "actual = config_hash(payload)" in approve_src
    assert re.search(r"set_approved_hash\([^)]*actual", approve_src), (
        "approve() no longer writes its own recomputed hash"
    )
    assert "body.config_hash != actual" in approve_src


def test_attack_trust_the_stored_config_hash_at_dispatch(router_src):
    """
    ATTACK: rely on dispatch reading the stored config_hash column rather than
    recomputing, so that anything able to write that column could authorise a
    run.

    HELD, and this is the strongest part of the design. dispatch recomputes
    from the answers as they are at dispatch time.
    """
    # ast.unparse normalises string quoting, so match quote-agnostically.
    dispatch_src = _function_source(router_src, "dispatch")
    assert "actual = config_hash(payload)" in dispatch_src
    assert not re.search(r"""row\.get\(['"]config_hash['"]\)""", dispatch_src), (
        "dispatch reads the stored config_hash instead of recomputing it"
    )
    assert re.search(r"""row\.get\(['"]approved_hash['"]\)""", dispatch_src)

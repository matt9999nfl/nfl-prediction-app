"""
The storage contract behind the approval guarantee — asserted against the SQL
that actually runs, not against a stand-in for it.

WHY THIS FILE EXISTS
--------------------
FINDING HC-S6-F1 got through 91 passing tests because every test of the
approval guarantee ran against an in-memory `Store` that cleared
`approved_hash`, while the real UPDATE never touched the column.  The fake was
kinder than production, so the test guarding the feature's core promise was
green while the promise was broken in the live service.

No test in this repository can execute BigQuery DML without credentials, so
what CAN be checked without them is checked here: the statement itself.  These
tests read app/queries/scoping.py and assert the properties the guarantee needs
the SQL to have.  Reverting the fix in that file turns this file red — which is
the whole point, and is the demonstration recorded in the handoff.

The live proof that the statement behaves this way against real BigQuery is
06-TESTING-QA/integration/test_hypothesis_chat.py, which needs ADC.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.queries import scoping as sq

QUERIES_SRC = Path(sq.__file__).read_text(encoding="utf-8")


def _function(name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(QUERIES_SRC)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"app/queries/scoping.py has no function {name!r}")


def _strings(name: str) -> str:
    return "\n".join(
        node.value
        for node in ast.walk(_function(name))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _statement(name: str) -> str:
    """
    The SQL the function issues.

    Identified by shape — a string constant whose first word is a statement
    keyword — rather than by size, because a docstring that discusses the
    statement is often longer than the statement.
    """
    candidates: list[str] = []
    for node in ast.walk(_function(name)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            candidates.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            # The table name is interpolated, so the statement is an f-string:
            # stitch its literal parts back together, with the substituted
            # pieces standing in as `?`.
            candidates.append("".join(
                part.value if isinstance(part, ast.Constant) else "?"
                for part in node.values
            ))
    statements = [c for c in candidates if c.strip().upper().startswith(("UPDATE ", "INSERT ", "SELECT "))]
    assert statements, f"{name} issues no statement"
    return max(statements, key=len)


# ── FINDING HC-S6-F1 ─────────────────────────────────────────────────────────


def test_update_answers_clears_the_stored_approval():
    """
    An answer change invalidates approval, and the invalidation must happen in
    storage.  The router cannot do it: dispatch compares against the STORED
    approved_hash, so a value cleared only on a response object is not cleared.
    """
    statement = _statement("update_answers")
    set_clause = statement[statement.upper().index("SET"):statement.upper().index("WHERE")]
    assert "approved_hash" in set_clause, (
        "update_answers does not clear approved_hash. An approval given for one "
        "brief survives into another, and dispatch will honour it."
    )
    assert "approved_hash = NULL" in set_clause.replace("\n", " ").replace("  ", " ") or \
           "approved_hash = NULL" in " ".join(set_clause.split()), (
        f"approved_hash appears in the SET clause but is not cleared: {set_clause}"
    )


def test_the_router_does_not_claim_the_clearing_itself():
    """
    The other half of F1: the router used to assign approved_hash=None to the
    dict it returned, so the API reported a cleared approval whether or not one
    had happened.  The response must be a report of the stored row.
    """
    router_src = (Path(sq.__file__).parents[1] / "routers" / "scoping.py").read_text(encoding="utf-8")
    answer_slot = next(
        ast.unparse(node)
        for node in ast.walk(ast.parse(router_src))
        if isinstance(node, ast.FunctionDef) and node.name == "answer_slot"
    )
    assert "'approved_hash': None" not in answer_slot and '"approved_hash": None' not in answer_slot, (
        "answer_slot still sets approved_hash on the response object. If the "
        "SQL ever stops clearing it, the API will keep saying it did."
    )


# ── FINDING HC-S6-F10 ────────────────────────────────────────────────────────


def test_the_approval_write_is_conditional_on_the_answers_it_approves():
    """
    Both endpoints read, decide, then write.  Without a condition on the write,
    an approve that loses a race to an answer lands anyway, attached to answers
    it was never computed from — and dispatch then refuses forever with nothing
    to explain why.
    """
    statement = _statement("set_approved_hash")
    where = statement.upper().index("WHERE")
    condition = statement[where:]
    assert "config_hash" in condition, (
        "set_approved_hash writes unconditionally. An approval that lost a race "
        "to an answer will still land, and wedge the session."
    )


def test_the_approval_write_reports_whether_it_landed():
    """A conditional write that nobody checks is an unconditional write."""
    source = ast.unparse(_function("set_approved_hash"))
    assert "_run_dml" in source, "set_approved_hash cannot see how many rows it changed"
    assert "return" in source, "set_approved_hash does not report the outcome"


def test_an_unknown_row_count_is_not_read_as_a_failed_write():
    """
    A client that cannot report a row count must not be read as "zero rows".
    Refusing a write nobody can prove failed would be its own silent failure,
    in the opposite direction.
    """
    class NoCount:
        def query(self, *_a, **_k):
            class Job:
                num_dml_affected_rows = None
                def result(self):
                    return []
            return Job()

    assert sq.set_approved_hash(NoCount(), "s", "h") is True


def test_a_zero_row_write_is_reported_as_a_lost_race():
    class ZeroRows:
        def query(self, *_a, **_k):
            class Job:
                num_dml_affected_rows = 0
                def result(self):
                    return []
            return Job()

    assert sq.set_approved_hash(ZeroRows(), "s", "h") is False


# ── the fake is only as kind as the thing it stands in for ───────────────────


def test_the_in_memory_store_behaves_the_way_the_real_sql_behaves():
    """
    The archetype, stated as an assertion.

    tests/test_scoping_api.py::Store reads these same two properties off the
    real statement rather than restating them, so the approval tests that run
    against it cannot pass on a kindness production does not extend.
    """
    from tests import test_scoping_api as impl

    assert impl._real_update_clears_approved_hash() is True, (
        "the real UPDATE no longer clears approved_hash — the guard tests in "
        "test_scoping_api.py are now passing for the wrong reason"
    )
    assert impl._real_approval_is_conditional() is True

    store = impl.Store()
    store.create_session(None, "s", "hypothesis")
    store.update_answers(None, "s", {"a": 1}, {"c": 1}, "hash-one", "assembled")
    assert store.set_approved_hash(None, "s", "approval", expected_config_hash="hash-one") is True
    assert store.rows["s"]["approved_hash"] == "approval"

    # An answer arrives: the stand-in must drop the approval, because the SQL does.
    store.update_answers(None, "s", {"a": 2}, {"c": 2}, "hash-two", "assembled")
    assert store.rows["s"]["approved_hash"] is None

    # And an approval computed from the old answers must not land.
    assert store.set_approved_hash(None, "s", "approval", expected_config_hash="hash-one") is False
    assert store.rows["s"]["approved_hash"] is None

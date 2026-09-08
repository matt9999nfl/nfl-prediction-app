"""
The archetype hunt on GET /api/v1/scoping/capability-gaps.

That endpoint is the one piece of Phase 6 currently live in production, and the
only evidence it works is that it returns 200 against an EMPTY table. That is
the exact shape the brief warns about: healthy on the case that happens to be
first, untested on the case that will actually occur.

So rather than wait for a row, the rows the implementation will produce are
built here — from the live feature catalog, through the real detect_gaps rule
engine, with the columns the INSERT and SELECT actually add — and validated
against the response model that will serialise them.

Result: this one is clean. Recorded as a checked-and-clear rather than left
unexamined.
"""
from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def backend_imports(backend_root):
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app.schemas.experiments import GameUniverseFilter
    from app.schemas.scoping import CapabilityGapListResponse
    from app.scoping import gaps as gaps_mod
    return gaps_mod, CapabilityGapListResponse, GameUniverseFilter


def _catalog(live_catalog):
    """Shaped the way app/routers/scoping.py::extract shapes it."""
    return [
        {
            "column": f["semantic_name"],
            "semantic_name": f["semantic_name"],
            "dataset": f["dataset"],
            "description": f.get("description", ""),
        }
        for f in live_catalog
    ]


def _persisted(gap: dict) -> dict:
    """A gap as GET /capability-gaps will return it: rule output + DB columns."""
    return {
        **gap,
        "gap_id": "00000000-0000-0000-0000-000000000001",
        "session_id": "00000000-0000-0000-0000-000000000002",
        "status": "open",
        "created_at": "2026-09-08T00:00:00+00:00",
    }


def test_the_first_real_gap_row_will_not_break_the_live_endpoint(
    backend_imports, live_catalog
):
    """
    Both gap kinds, through the response model.

    feature_catalog gaps carry null nearest_expressible and suggested_definition
    (HC-FINDINGS-S5 F-5, already ruled and owned by BACKEND-API). The question
    here is narrower and different: does that null 500 the endpoint? It does
    not — both fields are Optional on CapabilityGapOut.
    """
    gaps_mod, CapabilityGapListResponse, GameUniverseFilter = backend_imports
    catalog = _catalog(live_catalog)
    filterable = set(GameUniverseFilter.model_fields["field"].annotation.__args__)

    produced = gaps_mod.detect_gaps(
        unmatched_concepts=["offensive line weight"],
        catalog=catalog,
        requested_slices=["poor weather"],
        filterable_fields=filterable,
    )
    kinds = {gap["why_unavailable"] for gap in produced}
    assert kinds == {"feature_catalog", "filter_schema"}, (
        f"expected both gap kinds from Matt's hypothesis, got {kinds}"
    )

    response = CapabilityGapListResponse(data=[_persisted(gap) for gap in produced])
    assert len(response.data) == len(produced)
    assert any(row.nearest_expressible is None for row in response.data), (
        "no null-bearing row in this sample — the test is not exercising F-5's shape"
    )


def test_every_concept_alias_still_resolves_against_the_LIVE_catalog(
    backend_imports, live_catalog
):
    """
    A stale alias in concepts.json resolves to nothing and turns a corrected
    false gap back into a reported one — silently, because the wrong answer
    still looks like an answer.

    The implementation has a test for this against a catalog it builds itself;
    this runs it against the catalog the deployed service actually serves.
    """
    gaps_mod, _, _ = backend_imports
    live_names = {f["semantic_name"] for f in live_catalog}
    missing = [
        (entry["aliases"][0], feature)
        for entry in gaps_mod.load_concepts()
        for feature in entry["features"]
        if feature not in live_names
    ]
    assert not missing, (
        f"concepts.json points at features the live catalog does not have: {missing}"
    )


def test_the_gap_list_silently_truncates_at_two_hundred(backend_root):
    """
    Recorded, low severity. list_gaps applies `LIMIT 200` with no pagination
    and no total, so the 201st gap is invisible with no signal — and the gap
    list is meant to be the project's queue of missing features. Not a defect
    today (the table is empty); it is a slow one.
    """
    source = (backend_root / "app" / "queries" / "scoping.py").read_text(encoding="utf-8")
    assert "LIMIT 200" in source, "the limit changed — re-read this note"
    assert "next_cursor" not in source, "pagination was added — remove this note"

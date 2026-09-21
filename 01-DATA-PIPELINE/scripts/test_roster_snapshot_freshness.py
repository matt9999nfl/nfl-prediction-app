"""
Unit tests for the roster-snapshot three-state freshness check
(PROMPT-FIX-ROSTER-FRESHNESS-STATES.md, 2026-09-21).

Pure logic, no BigQuery import, no stubbing needed. Covers the defect that
broke B1-2's verification run: "dataset/table doesn't exist because the
capture was never deployed" must be a distinct, passing state -- not the
same failure as a capture that ran and then stopped.

Run:  python -m pytest 01-DATA-PIPELINE/scripts/test_roster_snapshot_freshness.py
  or: cd 01-DATA-PIPELINE/scripts && python -m pytest test_roster_snapshot_freshness.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from roster_snapshot_freshness import (  # noqa: E402
    ROSTER_SNAPSHOT_MAX_AGE_DAYS,
    evaluate_roster_snapshot_freshness,
)

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)


# ── State 1: dataset/table absent -- never deployed, not a failure ──────────


def test_absent_table_passes_as_not_deployed():
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=False, n_rows=0, latest=None, now=NOW,
    )
    assert ok is True
    assert state == "not deployed"


def test_absent_table_passes_even_with_stray_row_args():
    """table_exists is authoritative -- n_rows/latest are meaningless when
    the table itself doesn't exist, and must not be consulted."""
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=False, n_rows=999, latest=NOW, now=NOW,
    )
    assert ok is True
    assert state == "not deployed"


# ── State 2: present but empty, within the window -- not a failure yet ──────


def test_empty_and_just_created_passes_as_awaiting_first_capture():
    created = NOW - timedelta(hours=1)
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=0, latest=None, now=NOW, table_created=created,
    )
    assert ok is True
    assert state == "awaiting first capture"


def test_empty_at_exactly_the_boundary_passes():
    created = NOW - timedelta(days=ROSTER_SNAPSHOT_MAX_AGE_DAYS)
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=0, latest=None, now=NOW, table_created=created,
    )
    assert ok is True
    assert state == "awaiting first capture"


# ── State 3: stale -- the failure worth having ───────────────────────────────


def test_rows_exist_but_latest_is_stale_fails():
    latest = NOW - timedelta(days=ROSTER_SNAPSHOT_MAX_AGE_DAYS + 1)
    created = NOW - timedelta(days=60)
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=500, latest=latest, now=NOW, table_created=created,
    )
    assert ok is False
    assert state == "stale"


def test_rows_exist_and_fresh_passes():
    latest = NOW - timedelta(hours=1)
    created = NOW - timedelta(days=60)
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=500, latest=latest, now=NOW, table_created=created,
    )
    assert ok is True
    assert state == "fresh"


def test_empty_beyond_the_window_fails_as_stale():
    """The hole the prompt calls out: a table that exists and has NEVER had
    a single row must eventually fail, not pass forever."""
    created = NOW - timedelta(days=ROSTER_SNAPSHOT_MAX_AGE_DAYS + 1)
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=0, latest=None, now=NOW, table_created=created,
    )
    assert ok is False
    assert state == "stale"


def test_stale_still_reports_age_in_detail():
    latest = NOW - timedelta(days=ROSTER_SNAPSHOT_MAX_AGE_DAYS + 5)
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=10, latest=latest, now=NOW,
        table_created=NOW - timedelta(days=90),
    )
    assert ok is False
    assert f"{ROSTER_SNAPSHOT_MAX_AGE_DAYS + 5}.0 day" in detail


def test_no_rows_and_no_creation_time_fails_rather_than_guessing():
    """If neither a row timestamp nor a table-creation timestamp is
    available, there is no basis to call this anything but failing --
    silently passing on missing information would recreate the bug."""
    ok, state, detail = evaluate_roster_snapshot_freshness(
        table_exists=True, n_rows=0, latest=None, now=NOW, table_created=None,
    )
    assert ok is False
    assert state == "stale"

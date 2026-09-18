"""
Unit tests for the line-snapshot visibility guard
(PROMPT-FIX-SPREAD-SIGN-AND-LINE-SNAPSHOTS.md Part B.5): a stale or empty
raw_lines.line_snapshots must fail the pipeline's validation output, not only
show up in Cloud Logging (the HC-S6-F6 silent-failure pattern).

Pure logic, no BigQuery import, no stubbing needed.

Run:  python -m pytest 01-DATA-PIPELINE/scripts/test_line_snapshot_freshness.py
  or: cd 01-DATA-PIPELINE/scripts && python -m pytest test_line_snapshot_freshness.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from line_snapshot_freshness import (  # noqa: E402
    LINE_SNAPSHOT_MAX_AGE_DAYS,
    evaluate_line_snapshot_freshness,
)

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def test_empty_table_fails():
    """The exact state this stage found: 0 rows, table exists but never written to."""
    ok, age_txt = evaluate_line_snapshot_freshness(0, None, NOW)
    assert ok is False
    assert age_txt == "no rows"


def test_fresh_snapshot_passes():
    latest = NOW - timedelta(hours=1)
    ok, age_txt = evaluate_line_snapshot_freshness(100, latest, NOW)
    assert ok is True
    assert "0.0 day" in age_txt


def test_stale_snapshot_fails():
    latest = NOW - timedelta(days=LINE_SNAPSHOT_MAX_AGE_DAYS + 1)
    ok, age_txt = evaluate_line_snapshot_freshness(100, latest, NOW)
    assert ok is False
    assert f"{LINE_SNAPSHOT_MAX_AGE_DAYS + 1}.0 day" in age_txt


def test_exactly_at_the_boundary_passes():
    latest = NOW - timedelta(days=LINE_SNAPSHOT_MAX_AGE_DAYS)
    ok, _ = evaluate_line_snapshot_freshness(100, latest, NOW)
    assert ok is True

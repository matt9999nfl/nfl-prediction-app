"""
Tests for the section-3c fix (PROMPT-FIX-PIPELINE-IAM-AND-RETRY.md).

The 2026-09-18 B1-2 deploy failure (see QUESTIONS.md) traced to
`nfl-pipeline-sa` having no BigQuery grant on `raw_lines`. `snapshot_lines.py`
swallows that 403 by design, but the freshness query in `validate_and_report.py`
did not -- it raised straight out of `main()`, killing the container, and
Cloud Run's automatic retry turned one unreadable table into four full
pipeline reruns.

These tests cover both levels of the fix:
  - `fetch_line_snapshot_status()` in isolation: an unreadable table must
    return a failed status with the query error attached, never raise.
  - `main()` end-to-end with a fully-stubbed client: an unreadable table
    must produce a FAILED check in the written report (not an uncaught
    exception), `all_pass` must be False, and the report text must name
    both the dataset and the underlying error. A stale table must still
    fail and a fresh one must still pass -- the pre-existing behaviour
    this fix must not change.

Run:  python -m pytest 01-DATA-PIPELINE/scripts/test_validate_and_report.py
  or: cd 01-DATA-PIPELINE && python -m pytest scripts/test_validate_and_report.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# validate_and_report.py imports `from scripts.bq_utils import ...`, so the
# *parent* of scripts/ (01-DATA-PIPELINE) must be on sys.path -- not scripts/
# itself -- for that package-qualified import to resolve.
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import validate_and_report as var  # noqa: E402

RAW_LINES_ERROR = (
    "403 GET https://bigquery.googleapis.com/bigquery/v2/projects/"
    "nfl-model-471509/datasets/raw_lines?prettyPrint=false: Access Denied: "
    "Dataset nfl-model-471509:raw_lines: Permission bigquery.datasets.get "
    "denied on dataset nfl-model-471509:raw_lines (or it may not exist)."
)


# ── fetch_line_snapshot_status(): isolated, no full pipeline needed ──────────


class _RaisingClient:
    """query() always raises -- the exact shape of the 2026-09-18 failure."""

    def query(self, sql, *a, **k):
        # Mirrors the real google.api_core.exceptions.Forbidden -- a plain
        # Exception here proves fetch_line_snapshot_status catches broadly,
        # not just one narrow BigQuery exception type.
        raise Exception(RAW_LINES_ERROR)


class _FakeJob:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def to_dataframe(self):
        return self._df


class _RowClient:
    """query() returns a fixed one-row n_rows/latest frame."""

    def __init__(self, n_rows: int, latest):
        self._df = pd.DataFrame([{"n_rows": n_rows, "latest": latest}])

    def query(self, sql, *a, **k):
        return _FakeJob(self._df)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def test_unreadable_table_returns_failed_status_not_an_exception():
    """The core bug: this must not propagate the BigQuery exception."""
    ok, summary, error = var.fetch_line_snapshot_status(_RaisingClient(), now=NOW)
    assert ok is False
    assert error == RAW_LINES_ERROR
    assert summary != ""


def test_fresh_table_passes_with_no_error():
    ok, summary, error = var.fetch_line_snapshot_status(
        _RowClient(100, NOW - timedelta(hours=1)), now=NOW
    )
    assert ok is True
    assert error is None
    assert "100" in summary


def test_stale_table_fails_with_no_error():
    """Distinguish a genuinely stale table (query succeeded) from unreadable."""
    stale = NOW - timedelta(days=var.LINE_SNAPSHOT_MAX_AGE_DAYS + 1)
    ok, summary, error = var.fetch_line_snapshot_status(_RowClient(100, stale), now=NOW)
    assert ok is False
    assert error is None  # the query worked; the data is just old


def test_empty_table_fails_with_no_error():
    ok, summary, error = var.fetch_line_snapshot_status(_RowClient(0, None), now=NOW)
    assert ok is False
    assert error is None


# ── main() end-to-end: proves the report and all_pass, not just the helper ──


class FullPipelineFakeClient:
    """
    Stubs every query main() issues. Every per-season/per-bucket loop query
    (row counts, null rates, cover-rate bins) gets an empty frame back, so
    those loops contribute zero checks -- harmless, since the point of these
    tests is section 3c, not the rest of the report. The handful of queries
    that unpack a single row via `.iloc[0]` get exactly one row of
    trivially-passing data. Only the raw_lines.line_snapshots query varies.
    """

    def __init__(self, line_snapshots="fresh", age_days=0.1, n_rows=10):
        self._mode = line_snapshots  # "fresh" | "stale" | "empty" | "error"
        self._age_days = age_days
        self._n_rows = n_rows

    def query(self, sql, *a, **k):
        return _RoutingJob(sql, self)


class _RoutingJob:
    def __init__(self, sql: str, client: FullPipelineFakeClient):
        self.sql = sql
        self.client = client

    def to_dataframe(self):
        sql = self.sql
        c = self.client

        if "raw_lines.line_snapshots" in sql:
            if c._mode == "error":
                raise Exception(RAW_LINES_ERROR)
            if c._mode == "empty":
                return pd.DataFrame([{"n_rows": 0, "latest": None}])
            age = c._age_days if c._mode == "fresh" else var.LINE_SNAPSHOT_MAX_AGE_DAYS + 1
            latest = datetime.now(timezone.utc) - timedelta(days=age)
            return pd.DataFrame([{"n_rows": c._n_rows, "latest": latest}])

        if "raw_roster_snapshots." in sql:
            # Section 3d (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md, added 2026-09-19)
            # queries these two tables the same way -- COUNT(*)/MAX(captured_at),
            # unpacked via .iloc[0], which needs exactly one row back even from
            # a stub. These tests are about section 3c (line snapshots) only,
            # so always answer "fresh" here regardless of `c._mode` -- otherwise
            # every section-3c scenario would also have to reason about 3d.
            latest = datetime.now(timezone.utc) - timedelta(hours=1)
            return pd.DataFrame([{"n_rows": 10, "latest": latest}])

        if "qb_hit_nulls" in sql:
            return pd.DataFrame([{"qb_hit_nulls": 0, "sack_nulls": 0, "total": 100}])
        if "orphan_plays" in sql:
            return pd.DataFrame([{"orphan_plays": 0}])
        if "dupe_game_ids" in sql:
            return pd.DataFrame([{"dupe_game_ids": 0}])
        # Check the more specific "min_season" marker first -- "AS min_s" is
        # a literal substring of "AS min_season", so the order here matters.
        if "AS min_season" in sql:  # overall cover-rate check
            return pd.DataFrame([{
                "covers": 50, "total": 100, "cover_pct": 50.0,
                "min_season": 2015, "max_season": var.CURRENT_SEASON,
            }])
        if "AS min_s" in sql:  # season_range_in_scope
            return pd.DataFrame([{"min_s": 2015, "max_s": var.CURRENT_SEASON}])
        # Every remaining query is a per-season/per-bucket GROUP BY loop --
        # an empty frame makes the loop run zero times, contributing nothing.
        return pd.DataFrame()


def _run_and_capture(client, tmp_path, monkeypatch):
    report_path = tmp_path / "VALIDATION_REPORT.md"
    monkeypatch.setattr(var, "REPORT_PATH", report_path)
    exit_code = None
    try:
        var.main(client=client)
    except SystemExit as exc:
        exit_code = exc.code
    text = report_path.read_text(encoding="utf-8") if report_path.exists() else None
    return exit_code, text


def test_unreadable_raw_lines_fails_the_report_not_the_process(tmp_path, monkeypatch):
    exit_code, report = _run_and_capture(
        FullPipelineFakeClient(line_snapshots="error"), tmp_path, monkeypatch
    )

    # A controlled sys.exit(1) from "not all_pass" is expected and correct --
    # what must NOT happen is an uncaught BigQuery exception blowing past
    # main() entirely (which is what crashed the container on 2026-09-18).
    assert exit_code == 1

    # The report must have been written in full: main() did not die partway
    # through and skip sections 4-6.
    assert report is not None
    assert "6. Closing Line Source" in report

    assert "- line_snapshots_freshness" in report  # in the failed-checks list
    assert "❌ SOME CHECKS FAILED" in report

    # Names the dataset and the underlying error, per the prompt's acceptance line.
    assert "raw_lines.line_snapshots" in report
    assert RAW_LINES_ERROR in report


def test_stale_snapshot_still_fails_report(tmp_path, monkeypatch):
    exit_code, report = _run_and_capture(
        FullPipelineFakeClient(line_snapshots="stale"), tmp_path, monkeypatch
    )
    assert exit_code == 1
    assert "- line_snapshots_freshness" in report
    # A stale-but-readable table is not the same failure as an unreadable one.
    assert RAW_LINES_ERROR not in report


def test_fresh_snapshot_still_passes_report(tmp_path, monkeypatch):
    exit_code, report = _run_and_capture(
        FullPipelineFakeClient(line_snapshots="fresh"), tmp_path, monkeypatch
    )
    assert exit_code is None  # all_pass True -- main() never calls sys.exit
    assert "- line_snapshots_freshness" not in report
    assert "✅ ALL CHECKS PASSED" in report

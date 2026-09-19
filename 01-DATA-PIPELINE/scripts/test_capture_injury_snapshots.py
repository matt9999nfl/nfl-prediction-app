"""
Tests for capture_injury_snapshots.py (PROMPT-CAPTURE-INJURY-SNAPSHOTS.md).

Covers the three data traps the prompt calls out by name, all confirmed
against a live nflverse fetch on 2026-09-19, not just the archive:
  1. `report_status` uses the literal string "None" for ~half of all rows,
     not NULL -- must be captured and compared as a real value.
  2. `date_modified` can be null -- must not break capture; `captured_at` is
     the observation clock this stage provides and is never null.
  3. Depth charts are not unique per player-week -- a player can have several
     simultaneous `depth_position` rows, which must be tracked independently.

Run:  python -m pytest 01-DATA-PIPELINE/scripts/test_capture_injury_snapshots.py
"""
from __future__ import annotations

import os
import sys
import types

import pandas as pd

# scripts/__init__.py makes this a package, which means pytest's default
# import mode resolves the test module as `scripts.test_...` with
# 01-DATA-PIPELINE (not 01-DATA-PIPELINE/scripts) on sys.path -- too high up
# for a bare `import capture_injury_snapshots` to resolve. Add this file's
# own directory explicitly rather than depend on how pytest was invoked.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _install_bigquery_stub():
    """Stub google.cloud.bigquery so the module imports without credentials
    (same approach as test_snapshot_lines.py)."""
    google = sys.modules.get("google") or types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    bq = types.ModuleType("google.cloud.bigquery")

    class SchemaField:
        def __init__(self, name, field_type, mode="NULLABLE"):
            self.name = name
            self.field_type = field_type
            self.mode = mode

    class _Passthrough:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _Table:
        def __init__(self, *args, **kwargs):
            self.schema = []
            self.time_partitioning = None
            self.clustering_fields = None

    bq.SchemaField = SchemaField
    bq.LoadJobConfig = _Passthrough
    bq.WriteDisposition = types.SimpleNamespace(WRITE_APPEND="WRITE_APPEND")
    bq.Table = _Table
    bq.Dataset = _Table
    bq.TimePartitioning = _Passthrough
    bq.Client = object

    google.cloud = cloud
    cloud.bigquery = bq
    sys.modules.update({
        "google": google,
        "google.cloud": cloud,
        "google.cloud.bigquery": bq,
    })
    return bq


def _install_nfl_data_py_stub():
    """capture_injury_snapshots.py imports nfl_data_py at module level purely
    to call it inside fetch_injuries/fetch_depth_charts; tests never call
    those, so an empty stub is enough and keeps this test network-free."""
    mod = types.ModuleType("nfl_data_py")
    mod.import_injuries = lambda years: None
    mod.import_depth_charts = lambda years: None
    sys.modules["nfl_data_py"] = mod


_install_bigquery_stub()
_install_nfl_data_py_stub()

import capture_injury_snapshots as cap  # noqa: E402


# ── Trap 1: report_status's literal "None" string ─────────────────────────


def test_literal_none_string_is_not_treated_as_missing():
    """A row whose report_status is the string "None" must still be captured
    as a change when it differs from a real prior status -- and must not be
    silently equated with an actual null in either direction."""
    fetched = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "report_status": "None", "report_primary_injury": None,
         "report_secondary_injury": None, "practice_primary_injury": None,
         "practice_secondary_injury": None, "practice_status": None},
    ])
    latest = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "report_status": "Questionable", "report_primary_injury": None,
         "report_secondary_injury": None, "practice_primary_injury": None,
         "practice_secondary_injury": None, "practice_status": None},
    ])
    out = cap.rows_to_capture(fetched, latest, cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert len(out) == 1
    assert out.iloc[0]["report_status"] == "None"


def test_literal_none_string_does_not_equal_real_null():
    """The string "None" and an actual missing value are different states
    and must register as a change, not as "no change" (which real-NULL vs
    real-NULL correctly does -- see test_two_real_nulls_are_not_a_change)."""
    fetched = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "report_status": "None", "report_primary_injury": None,
         "report_secondary_injury": None, "practice_primary_injury": None,
         "practice_secondary_injury": None, "practice_status": None},
    ])
    latest = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "report_status": None, "report_primary_injury": None,
         "report_secondary_injury": None, "practice_primary_injury": None,
         "practice_secondary_injury": None, "practice_status": None},
    ])
    out = cap.rows_to_capture(fetched, latest, cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert len(out) == 1, "the literal string \"None\" must not be equated with a real null"


def test_two_real_nulls_are_not_a_change():
    """An unchanged null (e.g. report_secondary_injury staying empty) must
    not manufacture a new row on every re-run."""
    row = {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
           "report_status": "Out", "report_primary_injury": "Knee",
           "report_secondary_injury": None, "practice_primary_injury": "Knee",
           "practice_secondary_injury": None, "practice_status": "Did Not Participate"}
    fetched = pd.DataFrame([row])
    latest = pd.DataFrame([row])
    out = cap.rows_to_capture(fetched, latest, cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert out.empty


# ── Trap 2: null date_modified must not break capture ──────────────────────


def test_null_date_modified_is_captured_normally():
    """date_modified is informational only; a null value must not prevent
    the row from being fetched/kept, and captured_at (not date_modified) is
    what this script stamps."""
    df = pd.DataFrame([
        {"season": 2026, "week": 3, "game_type": "REG", "team": "KC", "gsis_id": "1",
         "full_name": "Player One", "position": "T",
         "report_primary_injury": "Knee", "report_secondary_injury": None,
         "report_status": "Out", "practice_primary_injury": "Knee",
         "practice_secondary_injury": None, "practice_status": "Did Not Participate",
         "date_modified": pd.NaT},
    ])
    # rows_to_capture doesn't touch date_modified at all (it isn't in
    # INJURY_COMPARE_COLS) -- this asserts that directly, since it's the
    # reason a null there can never affect whether a row is captured.
    assert "date_modified" not in cap.INJURY_COMPARE_COLS
    out = cap.rows_to_capture(df, pd.DataFrame(), cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert len(out) == 1
    assert pd.isna(out.iloc[0]["date_modified"])


# ── Trap 3: depth charts are not unique per player-week ─────────────────────


def test_multiple_depth_positions_for_one_player_week_are_independent():
    """A player listed at two depth_positions in the same week (e.g. a
    swing tackle at both LT and RT) must produce two tracked rows, not one
    overwriting the other -- depth_position is part of the key."""
    fetched = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "depth_position": "LT", "depth_team": "2", "formation": "Offense", "jersey_number": "79"},
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "depth_position": "RT", "depth_team": "1", "formation": "Offense", "jersey_number": "79"},
    ])
    out = cap.rows_to_capture(fetched, pd.DataFrame(), cap.DEPTH_CHART_KEY, cap.DEPTH_CHART_COMPARE_COLS)
    assert len(out) == 2
    assert set(out["depth_position"]) == {"LT", "RT"}


def test_one_depth_position_changing_does_not_touch_the_others():
    """Only the row whose depth_team actually changed should be re-captured;
    the player's other simultaneous depth_position entry, unchanged, must be
    dropped as a re-observation."""
    latest = pd.DataFrame([
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "depth_position": "LT", "depth_team": "2", "formation": "Offense", "jersey_number": "79"},
        {"season": 2026, "week": 3, "team": "KC", "gsis_id": "1",
         "depth_position": "RT", "depth_team": "1", "formation": "Offense", "jersey_number": "79"},
    ])
    fetched = latest.copy()
    fetched.loc[fetched["depth_position"] == "RT", "depth_team"] = "2"  # promoted

    out = cap.rows_to_capture(fetched, latest, cap.DEPTH_CHART_KEY, cap.DEPTH_CHART_COMPARE_COLS)
    assert len(out) == 1
    assert out.iloc[0]["depth_position"] == "RT"
    assert out.iloc[0]["depth_team"] == "2"


# ── General shape ────────────────────────────────────────────────────────


def test_first_ever_capture_keeps_every_row():
    fetched = pd.DataFrame([
        {"season": 2026, "week": 1, "team": "KC", "gsis_id": "1",
         "report_status": "Out", "report_primary_injury": "Knee",
         "report_secondary_injury": None, "practice_primary_injury": "Knee",
         "practice_secondary_injury": None, "practice_status": "Did Not Participate"},
        {"season": 2026, "week": 1, "team": "KC", "gsis_id": "2",
         "report_status": "None", "report_primary_injury": None,
         "report_secondary_injury": None, "practice_primary_injury": None,
         "practice_secondary_injury": None, "practice_status": "Full Participation"},
    ])
    out = cap.rows_to_capture(fetched, pd.DataFrame(), cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert len(out) == 2


def test_a_new_player_this_week_is_captured_even_when_others_are_unchanged():
    latest = pd.DataFrame([
        {"season": 2026, "week": 4, "team": "KC", "gsis_id": "1",
         "report_status": "Out", "report_primary_injury": "Knee",
         "report_secondary_injury": None, "practice_primary_injury": "Knee",
         "practice_secondary_injury": None, "practice_status": "Did Not Participate"},
    ])
    fetched = pd.concat([latest, pd.DataFrame([
        {"season": 2026, "week": 4, "team": "KC", "gsis_id": "2",
         "report_status": "Questionable", "report_primary_injury": "Ankle",
         "report_secondary_injury": None, "practice_primary_injury": "Ankle",
         "practice_secondary_injury": None, "practice_status": "Limited Participation"},
    ])], ignore_index=True)

    out = cap.rows_to_capture(fetched, latest, cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert len(out) == 1
    assert out.iloc[0]["gsis_id"] == "2"


def test_re_run_with_unchanged_source_data_adds_no_rows():
    """Acceptance criterion: a re-run with unchanged source data adds no
    rows. Simulates capture -> store -> re-fetch identical data."""
    row = {"season": 2026, "week": 5, "team": "KC", "gsis_id": "1",
           "report_status": "Out", "report_primary_injury": "Knee",
           "report_secondary_injury": None, "practice_primary_injury": "Knee",
           "practice_secondary_injury": None, "practice_status": "Did Not Participate"}
    first_capture = cap.rows_to_capture(pd.DataFrame([row]), pd.DataFrame(), cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert len(first_capture) == 1

    second_capture = cap.rows_to_capture(pd.DataFrame([row]), first_capture, cap.INJURY_KEY, cap.INJURY_COMPARE_COLS)
    assert second_capture.empty


def test_depth_chart_schema_key_and_compare_cols_do_not_overlap():
    """A column can't be both an identity key and a compared value -- that
    would make a change in it look like a new, unrelated row instead of an
    update to the same one."""
    assert set(cap.DEPTH_CHART_KEY).isdisjoint(cap.DEPTH_CHART_COMPARE_COLS)
    assert set(cap.INJURY_KEY).isdisjoint(cap.INJURY_COMPARE_COLS)


def test_injury_and_depth_chart_schemas_declare_captured_at_required():
    for schema in (cap.INJURY_SCHEMA, cap.DEPTH_CHART_SCHEMA):
        by_name = {f.name: f for f in schema}
        assert by_name["captured_at"].mode == "REQUIRED"

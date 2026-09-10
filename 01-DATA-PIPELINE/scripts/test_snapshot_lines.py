"""
Regression tests for the line-snapshot query construction.

These build the SQL with a stubbed BigQuery client and assert its shape. They
need no credentials and no network, which is the point: the first live run of
snapshot_lines.py failed with

    400 Query column 3 has type FLOAT64 which cannot be inserted into column
    week, which has type INT64

because raw_nflfastr.schedules is loaded with schema autodetect from pandas, and
pandas represents a nullable integer column as float64. Every nullable int at
source -- week, and every moneyline and odds field -- arrives as FLOAT64.

No unit test against a fake could have caught the original: the fake did not
model column types. What these tests protect instead is that the casts stay
present, which is cheap and catches the regression if someone simplifies the
query later.

Run:  python -m pytest 01-DATA-PIPELINE/scripts/test_snapshot_lines.py
"""
from __future__ import annotations

import re
import sys
import types


def _install_bigquery_stub():
    """Stub google.cloud.bigquery so the module imports without credentials."""
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
    bq.ScalarQueryParameter = _Passthrough
    bq.ArrayQueryParameter = _Passthrough
    bq.QueryJobConfig = _Passthrough
    bq.LoadJobConfig = _Passthrough
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


_BQ = _install_bigquery_stub()

import snapshot_lines as sl  # noqa: E402


class _FakeJob:
    num_dml_affected_rows = 3

    def result(self):
        return None


class FakeClient:
    """Records the SQL it is asked to run; reports whichever columns we choose."""

    def __init__(self, present_columns=None):
        self._present = present_columns
        self.sql = None

    def create_dataset(self, *a, **k):
        pass

    def create_table(self, *a, **k):
        pass

    def get_table(self, name):
        table = _BQ.Table()
        cols = self._present if self._present is not None else list(sl.MARKET_FIELDS)
        base = ["game_id", "season", "week", "home_team", "away_team",
                "home_score", "away_score"]
        table.schema = [_BQ.SchemaField(n, "STRING") for n in base + cols]
        return table

    def query(self, sql, job_config=None):
        self.sql = sql
        return _FakeJob()


def _build_sql(present_columns=None, seasons=None) -> str:
    client = FakeClient(present_columns)
    sl.snapshot(client, seasons=seasons)
    assert client.sql is not None
    return client.sql


# ── The bug that actually happened ────────────────────────────────────────────


def test_week_and_season_are_cast_to_int64():
    """The live failure. pandas turns nullable ints into float64 on load."""
    sql = _build_sql()
    assert "SAFE_CAST(s.week AS INT64) AS week" in sql
    assert "SAFE_CAST(s.season AS INT64) AS season" in sql


def test_every_market_field_is_cast_to_its_declared_type():
    sql = _build_sql()
    for field, target in sl.FIELD_TYPES.items():
        assert f"SAFE_CAST(s.{field} AS {target}) AS {field}" in sql, field


def test_field_types_covers_every_market_field():
    """FIELD_TYPES and MARKET_FIELDS must not drift apart."""
    assert set(sl.FIELD_TYPES) == set(sl.MARKET_FIELDS)


def test_declared_types_match_the_table_schema():
    """The cast target must be what the column actually is."""
    bq_to_sql = {"FLOAT": "FLOAT64", "INTEGER": "INT64"}
    by_name = {f.name: f.field_type for f in sl.SCHEMA}
    for field, target in sl.FIELD_TYPES.items():
        assert bq_to_sql[by_name[field]] == target, field


# ── Shape of the insert ───────────────────────────────────────────────────────


def test_insert_column_count_matches_select_count():
    """A mismatch here is the other way this query fails at runtime."""
    sql = _build_sql()
    target = re.search(r"INSERT INTO[^(]*\((.*?)\)", sql, re.S).group(1)
    n_target = len([c for c in target.replace("\n", " ").split(",") if c.strip()])
    assert n_target == 15, n_target


def test_missing_columns_become_typed_nulls():
    """nflverse has added odds fields over time; absent ones must not break the run."""
    sql = _build_sql(present_columns=["spread_line", "total_line"])
    assert "CAST(NULL AS INT64) AS home_moneyline" in sql
    assert "SAFE_CAST(s.spread_line AS FLOAT64)" in sql


def test_absent_spread_line_aborts_rather_than_writing_empty_rows():
    result = sl.snapshot(FakeClient(present_columns=["total_line"]))
    assert result["status"] == "NO_SPREAD_COLUMN"
    assert result["inserted"] == 0


# ── Change-log semantics ──────────────────────────────────────────────────────


def test_null_transitions_count_as_changes():
    """
    IS DISTINCT FROM, not !=.

    A line appearing (null -> 3.5) or being pulled (3.5 -> null) is exactly the
    movement worth recording, and `!=` returns NULL for both, which the WHERE
    clause would discard silently.
    """
    sql = _build_sql()
    for field in sl.MARKET_FIELDS:
        assert f"latest.{field} IS DISTINCT FROM src.{field}" in sql, field
    assert "!=" not in sql


def test_only_the_latest_snapshot_per_game_is_compared():
    sql = _build_sql()
    assert "PARTITION BY l.game_id ORDER BY l.captured_at DESC" in sql
    assert "WHERE rn = 1" in sql


def test_first_ever_snapshot_is_inserted():
    """LEFT JOIN + IS NULL — without it the table could never take a first row."""
    assert "WHERE latest.game_id IS NULL" in _build_sql()


def test_game_completed_change_is_recorded():
    """The transition to completed is what marks the settled closing line."""
    assert "latest.game_completed IS DISTINCT FROM src.game_completed" in _build_sql()


def test_season_filter_is_parameterised():
    assert "s.season IN UNNEST(@seasons)" in _build_sql(seasons=[2026])
    assert "@seasons" not in _build_sql(seasons=None)

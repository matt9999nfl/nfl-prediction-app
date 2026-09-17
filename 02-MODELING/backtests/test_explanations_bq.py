"""
Unit tests for backtests/explanations_bq.py's write_explanations() — the
reproduction_max_diff / is_approximate columns (STAGE 1 follow-up,
2026-09-17) and clean_forward's untouched meaning. No BigQuery network calls:
the client's load_table_from_dataframe is replaced with a fake that just
captures the DataFrame it was given.

Run:
    cd 02-MODELING && python -m pytest backtests/test_explanations_bq.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtests import explanations_bq as ebq  # noqa: E402


class _FakeJob:
    def result(self):
        return None


class _FakeClient:
    def __init__(self):
        self.captured_df = None
        self.captured_job_config = None

    def load_table_from_dataframe(self, df, table_id, job_config=None):
        self.captured_df = df.copy()
        self.captured_job_config = job_config
        return _FakeJob()


def _minimal_exp_df(game_ids=("G1", "G2")):
    rows = []
    for gid in game_ids:
        rows.append({
            "game_id": gid, "season": 2026, "week": 1, "feature": "home_ol_sack_rate",
            "side": "home", "family": "OL pass protection", "raw_value": 0.1,
            "league_pctile": 50.0, "was_imputed": False, "contribution_logodds": 0.05,
            "pick_direction_contribution": 0.05, "abs_rank": 1, "bias_logodds": -0.1,
            "predicted_side": "home", "predicted_home_cover_prob": 0.55,
        })
    return pd.DataFrame(rows)


def test_schema_declares_the_new_columns_as_required_and_nullable_respectively():
    fields = {f.name: f for f in ebq.EXPLANATIONS_SCHEMA}
    assert fields["reproduction_max_diff"].field_type == "FLOAT64"
    assert fields["reproduction_max_diff"].mode == "NULLABLE"
    assert fields["is_approximate"].field_type == "BOOL"
    assert fields["is_approximate"].mode == "REQUIRED"


def test_defaults_are_null_diff_and_not_approximate():
    client = _FakeClient()
    ebq.write_explanations(
        client, _minimal_exp_df(),
        run_id="r1", experiment_id="e1", model_name="ol_xgb_v2",
        feature_list_hash="abc123", blend_n=8,
    )
    out = client.captured_df
    assert out["reproduction_max_diff"].isna().all()
    assert (out["is_approximate"] == False).all()  # noqa: E712


def test_explicit_reproduction_values_are_written():
    client = _FakeClient()
    ebq.write_explanations(
        client, _minimal_exp_df(),
        run_id="r1", experiment_id="e1", model_name="ol_xgb_v2",
        feature_list_hash="abc123", blend_n=8,
        reproduction_max_diff=0.0966565,
        is_approximate=True,
    )
    out = client.captured_df
    assert out["reproduction_max_diff"].astype(float).tolist() == pytest.approx([0.0966565, 0.0966565])
    assert (out["is_approximate"] == True).all()  # noqa: E712


def test_clean_forward_is_independent_of_is_approximate():
    # An approximate write with a per-game clean_forward map must not have
    # clean_forward silently forced to False by is_approximate=True — the two
    # columns are orthogonal.
    client = _FakeClient()
    ebq.write_explanations(
        client, _minimal_exp_df(game_ids=("G1", "G2")),
        run_id="r1", experiment_id="e1", model_name="ol_xgb_v2",
        feature_list_hash="abc123", blend_n=8,
        clean_forward={"G1": True, "G2": False},
        reproduction_max_diff=0.05,
        is_approximate=True,
    )
    out = client.captured_df.set_index("game_id")
    assert bool(out.loc["G1", "clean_forward"]) is True
    assert bool(out.loc["G2", "clean_forward"]) is False
    assert (client.captured_df["is_approximate"] == True).all()  # noqa: E712

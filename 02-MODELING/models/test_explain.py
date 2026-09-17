"""
Unit tests for OLXGBModel.explain() / explain_interactions() (STAGE 1.1 of
PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md). Synthetic data only — no BigQuery.

Run:
    cd 02-MODELING && python -m pytest models/test_explain.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models.ol_xgb import OLXGBModel, EXPLAIN_SUM_TOLERANCE  # noqa: E402


def _synthetic_frame(n=400, n_features=6, seed=0):
    rng = np.random.default_rng(seed)
    cols = [f"feat_{i}" for i in range(n_features)]
    X = pd.DataFrame(rng.normal(size=(n, n_features)), columns=cols)
    # y correlated with feat_0 and feat_1 so the model has real signal to attribute
    logit = 1.5 * X["feat_0"] - 0.8 * X["feat_1"] + rng.normal(scale=0.3, size=n)
    y = (logit > 0).astype(int)
    return X, pd.Series(y)


@pytest.fixture(scope="module")
def fitted_model():
    X, y = _synthetic_frame()
    model = OLXGBModel(random_seed=42)
    model.fit(X, y)
    return model, X


def test_contributions_sum_to_log_odds(fitted_model):
    model, X = fitted_model
    exp = model.explain(X.iloc[:20])
    # bias + sum(contributions) per row should equal row_sum_logodds, which
    # the method itself already asserts against the model's raw margin.
    per_row = exp.groupby("row").agg(
        bias=("bias_logodds", "first"),
        total=("contribution_logodds", "sum"),
        asserted_sum=("row_sum_logodds", "first"),
    )
    reconstructed = per_row["bias"] + per_row["total"]
    assert np.allclose(reconstructed, per_row["asserted_sum"], atol=1e-6)


def test_explain_raises_on_row_sum_mismatch(monkeypatch, fitted_model):
    model, X = fitted_model

    booster = model.model.get_booster()
    real_predict = booster.predict

    def _tampered_predict(dm, **kwargs):
        out = real_predict(dm, **kwargs)
        if kwargs.get("output_margin"):
            return out + 10.0  # force a mismatch against the untouched contributions
        return out

    monkeypatch.setattr(booster, "predict", _tampered_predict)
    with pytest.raises(AssertionError, match="do not sum to the model's raw log-odds"):
        model.explain(X.iloc[:5])


def test_was_imputed_flag_set_only_for_nan_inputs(fitted_model):
    model, X = fitted_model
    X_missing = X.iloc[:10].copy()
    X_missing.loc[X_missing.index[0], "feat_0"] = np.nan
    X_missing.loc[X_missing.index[1], "feat_2"] = np.nan

    exp = model.explain(X_missing)
    flagged = exp[exp["was_imputed"]]
    flagged_pairs = set(zip(flagged["row"], flagged["feature"]))
    assert flagged_pairs == {
        (X_missing.index[0], "feat_0"),
        (X_missing.index[1], "feat_2"),
    }


def test_abs_rank_is_a_valid_permutation_per_row(fitted_model):
    model, X = fitted_model
    exp = model.explain(X.iloc[:5])
    for _, group in exp.groupby("row"):
        assert sorted(group["abs_rank"]) == list(range(1, len(group) + 1))
        # rank 1 must have the largest |contribution|
        top = group.loc[group["abs_rank"] == 1, "contribution_logodds"].iloc[0]
        assert abs(top) == group["contribution_logodds"].abs().max()


def test_explain_on_unfitted_model_raises():
    model = OLXGBModel(random_seed=42)
    X, _ = _synthetic_frame(n=5)
    with pytest.raises(RuntimeError):
        model.explain(X)


def test_explain_interactions_shape_and_ranking(fitted_model):
    model, X = fitted_model
    inter = model.explain_interactions(X.iloc[:5], top_k=3)
    assert set(inter.columns) == {"row", "feature_a", "feature_b", "interaction_logodds", "abs_rank"}
    for _, group in inter.groupby("row"):
        assert len(group) <= 3
        assert sorted(group["abs_rank"]) == list(range(1, len(group) + 1))
        vals = group.sort_values("abs_rank")["interaction_logodds"].abs().tolist()
        assert vals == sorted(vals, reverse=True)


def test_tolerance_constant_is_1e_minus_4():
    assert EXPLAIN_SUM_TOLERANCE == 1e-4

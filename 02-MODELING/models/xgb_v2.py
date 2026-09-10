"""
XGBoost cover-probability model — Phase 1 v2 (comprehensive feature set).

Inherits all behaviour from OLXGBModel (ol_xgb_v1).  The only differences:
  - name = "ol_xgb_v2"
  - Slightly relaxed min_child_weight (8 vs 10) to allow the model to use
    the expanded feature set without over-regularising; all other params
    stay conservative for the same reason as v1 (small n per fold).

All leakage guarantees from v1 are preserved: scaler + imputer are fit on
training data only, applied to test.
"""

from models.ol_xgb import OLXGBModel

XGB_PARAMS_V2 = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.03,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=8,       # slightly relaxed vs v1's 10
    reg_alpha=0.1,
    reg_lambda=1.0,
    eval_metric="logloss",
    random_state=42,
    # n_jobs is pinned to 1, NOT -1.
    #
    # With n_jobs=-1 XGBoost uses every available core, and its histogram
    # builder sums gradients in thread-completion order. A different core count
    # therefore changes floating-point rounding, which changes split points,
    # which compounds over 300 boosting rounds. Observed 2026-09-10: identical
    # code, identical BigQuery data and random_state=42 produced different
    # probabilities on a 12-core laptop than on a 2-core Cloud Run job — all 16
    # week-1 games differed, by up to 0.042, and two picks flipped sides. Two
    # runs on the SAME machine matched exactly, which is what made it look like
    # a library problem rather than a threading one.
    #
    # random_state does not protect against this: it seeds sampling, not thread
    # scheduling.
    #
    # This platform exists to measure whether a model has an edge. A backtest
    # whose result depends on the core count of the machine that ran it is not
    # measuring the model. Single-threaded costs about a second on 2,822 rows —
    # nothing against reproducibility.
    #
    # tree_method is stated explicitly for the same reason: leaving it to the
    # default means the algorithm can change under an XGBoost upgrade.
    n_jobs=1,
    tree_method="hist",
)


class OLXGBModelV2(OLXGBModel):
    """Comprehensive v2 XGBoost model — drops in to the walk-forward harness."""

    name = "ol_xgb_v2"

    def __init__(self, params=None, random_seed: int = 42):
        p = dict(params or XGB_PARAMS_V2)
        p["random_state"] = random_seed
        super().__init__(params=p, random_seed=random_seed)

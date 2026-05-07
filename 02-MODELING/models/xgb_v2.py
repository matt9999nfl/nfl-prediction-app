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
    n_jobs=-1,
)


class OLXGBModelV2(OLXGBModel):
    """Comprehensive v2 XGBoost model — drops in to the walk-forward harness."""

    name = "ol_xgb_v2"

    def __init__(self, params=None):
        super().__init__(params=params or XGB_PARAMS_V2)

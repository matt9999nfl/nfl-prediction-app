"""
XGBoost cover-probability model — Phase 1 first pass.

Architecture decision
---------------------
XGBoost classifier with conservative hyperparameters chosen to avoid
overfitting on what amounts to ~1,000–1,100 training games per fold.
No hyperparameter search in Phase 1; run one clean model, measure the
gate, refine only after seeing where the signal lives.

Tuning note (post gate review)
-------------------------------
If the gate is missed, do NOT tune hyperparameters blindly.  First look at
feature importance (permutation or gain) to see whether the OL features are
pulling any weight at all.  If not, the hypothesis may need to be revisited
before the model architecture does.

Output
------
predict_proba returns P(home team covers closing spread).
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# Tolerance for the TreeSHAP row-sum assertion in explain(): contributions for
# a row must sum to that row's raw log-odds margin to within this much.  1e-4
# per STAGE 1.1 of PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md.
EXPLAIN_SUM_TOLERANCE = 1e-4

logger = logging.getLogger(__name__)

# Conservative first-pass hyperparameters
# min_child_weight=10 is the primary regularizer given small n
XGB_PARAMS = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.03,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=10,
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


class OLXGBModel:
    """
    XGBoost cover-probability model with integrated scaling and imputation.

    The scaler and imputer are fit on the TRAINING set and applied to test.
    Call fit() on training data, then predict_proba() on test data.
    """

    name = "ol_xgb_v1"

    def __init__(self, params: Optional[dict] = None, random_seed: int = 42):
        p = dict(params or XGB_PARAMS)
        p["random_state"] = random_seed
        self.params = p
        self.scaler   = StandardScaler()
        self.imputer  = SimpleImputer(strategy="mean")
        self.model    = XGBClassifier(**self.params)
        self._feature_names: list[str] = []
        self._fitted = False

    def _preprocess_fit(self, X: pd.DataFrame) -> np.ndarray:
        """Fit scaler + imputer on training data, return transformed array."""
        Xf = self.imputer.fit_transform(X)
        Xf = self.scaler.fit_transform(Xf)
        return Xf

    def _preprocess_transform(self, X: pd.DataFrame) -> np.ndarray:
        """Apply already-fitted scaler + imputer to test data."""
        if not self._fitted:
            raise RuntimeError("Model not fitted — call fit() first")
        Xf = self.imputer.transform(X)
        Xf = self.scaler.transform(Xf)
        return Xf

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "OLXGBModel":
        """
        Fit the model.

        Parameters
        ----------
        X_train : DataFrame of feature columns (NaN allowed; will be imputed)
        y_train : Series of 0/1 labels (1 = home covered)
        """
        self._feature_names = list(X_train.columns)
        Xf = self._preprocess_fit(X_train)
        logger.info(
            f"Fitting XGBoost on {len(X_train):,} games, "
            f"{len(self._feature_names)} features …"
        )
        self.model.fit(Xf, y_train.values)
        self._fitted = True
        return self

    def predict_proba(self, X_test: pd.DataFrame) -> np.ndarray:
        """Return P(home covers) for each row in X_test."""
        Xf = self._preprocess_transform(X_test)
        return self.model.predict_proba(Xf)[:, 1]

    def feature_importance(self) -> pd.DataFrame:
        """
        Return a DataFrame of feature importances (XGBoost gain-based).

        Sorted descending by importance.
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted")
        scores = self.model.feature_importances_
        return (
            pd.DataFrame({"feature": self._feature_names, "importance": scores})
            .sort_values("importance", ascending=False)
            .reset_index(drop=True)
        )

    def get_params(self) -> dict:
        return {
            "model_type": "xgboost",
            "hyperparameters": self.params,
        }

    # ── Per-game explanations (STAGE 1) ─────────────────────────────────────

    def explain(self, X_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Exact per-row TreeSHAP contributions, computed natively by XGBoost
        (no new dependency — booster.predict(..., pred_contribs=True)).

        Long format: one row per (input row, feature). Columns:
            row                    — X_raw.index value for this input row
            feature                — column name from X_raw
            raw_value              — the value actually fed to the tree, in
                                      original units (imputed, NOT scaled)
            was_imputed            — True if the original X_raw value was NaN
            contribution_logodds   — this feature's exact SHAP contribution
                                      to the row's raw log-odds output
            bias_logodds           — the row's bias term (same for every
                                      feature in a row; xgboost's constant)
            row_sum_logodds        — bias + sum(contributions); asserted to
                                      equal the model's raw margin for that row
            abs_rank               — 1 = largest |contribution| in that row

        Contributions are computed on the scaled/imputed matrix the booster
        actually saw; raw_value is stored in original units so a report never
        has to un-scale a StandardScaler value to be readable.

        Raises AssertionError if any row's contributions do not sum to that
        row's raw log-odds margin within EXPLAIN_SUM_TOLERANCE — a mismatch
        here means the preprocessing used for explanation diverged from what
        the model actually saw, and nothing should be stored.
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted — call fit() first")

        X_raw = X_raw[self._feature_names]
        raw_values = X_raw.to_numpy(dtype=float)
        was_imputed = np.isnan(raw_values)

        Xf_imputed = self.imputer.transform(X_raw)   # unscaled, imputed — original units
        Xf_scaled = self.scaler.transform(Xf_imputed)  # what the booster saw

        booster = self.model.get_booster()
        dm = xgb.DMatrix(Xf_scaled)
        contribs = booster.predict(dm, pred_contribs=True)  # (n, n_features + 1)
        margin = booster.predict(dm, output_margin=True)    # (n,) raw log-odds

        row_sums = contribs.sum(axis=1)
        max_err = float(np.max(np.abs(row_sums - margin))) if len(margin) else 0.0
        if max_err > EXPLAIN_SUM_TOLERANCE:
            raise AssertionError(
                f"TreeSHAP contributions do not sum to the model's raw log-odds "
                f"margin (max abs error {max_err:.3g} > {EXPLAIN_SUM_TOLERANCE:.0e}). "
                "Refusing to emit explanations that would not describe this model."
            )

        n_rows, n_feats = Xf_imputed.shape
        records = []
        for i in range(n_rows):
            bias = float(contribs[i, -1])
            row_contribs = contribs[i, :-1]
            order = np.argsort(-np.abs(row_contribs))
            rank_of = np.empty(n_feats, dtype=int)
            rank_of[order] = np.arange(1, n_feats + 1)
            row_id = X_raw.index[i]
            for j, feat in enumerate(self._feature_names):
                records.append({
                    "row": row_id,
                    "feature": feat,
                    "raw_value": float(Xf_imputed[i, j]),
                    "was_imputed": bool(was_imputed[i, j]),
                    "contribution_logodds": float(row_contribs[j]),
                    "bias_logodds": bias,
                    "row_sum_logodds": float(row_sums[i]),
                    "abs_rank": int(rank_of[j]),
                })
        return pd.DataFrame.from_records(records)

    def explain_interactions(self, X_raw: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
        """
        Exact per-row TreeSHAP interaction values (booster.predict(...,
        pred_interactions=True)), reduced to the top_k strongest off-diagonal
        feature pairs per row.

        This is O(n_features^2) per row — call it for the week-1 slate and
        backtest summaries only, never for every live weekly row (STAGE 1.1).

        Returns one row per (input row, pair), columns:
            row, feature_a, feature_b, interaction_logodds, abs_rank
        interaction_logodds is 2x the raw off-diagonal SHAP-interaction value
        (the matrix is symmetric off-diagonal; the two halves are combined
        into one number per unordered pair, matching how the diagonal already
        represents each feature's own main effect).
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted — call fit() first")

        X_raw = X_raw[self._feature_names]
        Xf_imputed = self.imputer.transform(X_raw)
        Xf_scaled = self.scaler.transform(Xf_imputed)

        booster = self.model.get_booster()
        dm = xgb.DMatrix(Xf_scaled)
        inter = booster.predict(dm, pred_interactions=True)  # (n, F+1, F+1)

        feat_names = self._feature_names
        n_feats = len(feat_names)
        records = []
        for i in range(inter.shape[0]):
            mat = inter[i, :n_feats, :n_feats]  # drop the bias row/col
            pairs = []
            for a in range(n_feats):
                for b in range(a + 1, n_feats):
                    val = float(mat[a, b] + mat[b, a])
                    pairs.append((a, b, val))
            pairs.sort(key=lambda t: -abs(t[2]))
            row_id = X_raw.index[i]
            for rank, (a, b, val) in enumerate(pairs[:top_k], start=1):
                records.append({
                    "row": row_id,
                    "feature_a": feat_names[a],
                    "feature_b": feat_names[b],
                    "interaction_logodds": val,
                    "abs_rank": rank,
                })
        return pd.DataFrame.from_records(records)

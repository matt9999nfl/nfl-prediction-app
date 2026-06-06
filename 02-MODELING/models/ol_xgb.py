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
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

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
    n_jobs=-1,
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

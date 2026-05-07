"""
Naive baseline models.

These exist solely to establish the null comparison required by the backtest
spec.  Every reported model result must be shown alongside these baselines.

AlwaysHomeBaseline
  Always predicts the home team covers.
  ATS record on the same game set establishes whether home-field alone
  provides a systematic edge that the real model must beat.
"""

import numpy as np
import pandas as pd


class AlwaysHomeBaseline:
    """Predict home covers with probability 1.0 for every game."""

    name = "always_home_baseline"

    def predict_proba(self, n_games: int) -> np.ndarray:
        """Return an (n_games,) array of constant 1.0 probabilities."""
        return np.ones(n_games)

    def score_games(self, games_df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply this baseline to a game DataFrame that includes home_covered.

        Columns added:
          baseline_predicted_side       — always 'home'
          baseline_correct              — 1 / 0 / NaN (push)
        """
        out = games_df.copy()
        out["baseline_predicted_side"] = "home"
        out["baseline_correct"] = out["home_covered"].map(
            lambda x: None if pd.isna(x) else (1 if x else 0)
        )
        return out

    @staticmethod
    def ats_record(games_df: pd.DataFrame) -> dict:
        """Return wins, losses, pushes and hit_rate for the always-home baseline."""
        decided = games_df.dropna(subset=["home_covered"])
        wins   = int(decided["home_covered"].astype(int).sum())
        losses = int(len(decided) - wins)
        pushes = int(games_df["home_covered"].isna().sum())
        n      = wins + losses
        return {
            "wins":     wins,
            "losses":   losses,
            "pushes":   pushes,
            "n_games":  n,
            "hit_rate": wins / n if n > 0 else float("nan"),
        }

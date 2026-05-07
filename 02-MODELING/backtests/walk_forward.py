"""
Walk-forward backtest harness — Phase 1 / Phase 2.

Phase 1 fold structure (non-negotiable per MODELING_SPEC_PHASE1):
  Fold 1: train 2015–2018, test 2019
  Fold 2: train 2016–2019, test 2020
  Fold 3: train 2017–2020, test 2021
  Fold 4: train 2018–2021, test 2022
  Fold 5: train 2019–2022, test 2023
  Fold 6: train 2020–2023, test 2024

Phase 2 note: run_walk_forward() now accepts an optional ``folds_override``
parameter so that config-driven runners can derive folds dynamically from
``platform.experiment_configs`` (via ``build_folds_from_config``).  When
``folds_override`` is omitted the function falls back to the hardcoded
``FOLDS`` constant above, keeping ``run_phase1_backtest.py`` unchanged.

Leakage guarantees
------------------
- train/test split is strictly by season (no game crosses the boundary)
- StandardScaler and SimpleImputer are fit on training games only
- Closing spread is the LABEL, not a feature
- ol_mismatch_flag is set to 0 for all predictions (awaiting approval)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from features.ol_metrics import ALL_MODEL_FEATURES
from models.baselines import AlwaysHomeBaseline
from models.ol_xgb import OLXGBModel  # default; callers may pass a different class

logger = logging.getLogger(__name__)

# ── Fold definitions ─────────────────────────────────────────────────────────

FOLDS: list[tuple[list[int], int]] = [
    ([2015, 2016, 2017, 2018], 2019),
    ([2016, 2017, 2018, 2019], 2020),
    ([2017, 2018, 2019, 2020], 2021),
    ([2018, 2019, 2020, 2021], 2022),
    ([2019, 2020, 2021, 2022], 2023),
    ([2020, 2021, 2022, 2023], 2024),
]

PHASE2_GATE_HIT_RATE   = 0.54
PHASE2_GATE_MIN_GAMES  = 250


# ── Config-driven fold builder ────────────────────────────────────────────────

def build_folds_from_config(
    start_season: int,
    end_season: int,
    train_seasons: int,
    test_seasons: int = 1,
) -> list[tuple[list[int], int]]:
    """
    Derive the walk-forward fold list from experiment config parameters.

    Parameters
    ----------
    start_season   : First season in the historical window (data availability start).
    end_season     : Last season to evaluate (inclusive).
    train_seasons  : Number of seasons in each training window.
    test_seasons   : Number of seasons per test fold (almost always 1).

    Returns
    -------
    List of (train_season_list, test_season) tuples, same shape as FOLDS.

    Example
    -------
    build_folds_from_config(2015, 2024, train_seasons=4, test_seasons=1)
    → same 6 folds as the hardcoded FOLDS constant.
    """
    folds: list[tuple[list[int], int]] = []
    first_test = start_season + train_seasons
    test = first_test
    while test <= end_season:
        train = list(range(test - train_seasons, test))
        folds.append((train, test))
        test += test_seasons
    return folds


# ── Result containers ────────────────────────────────────────────────────────

@dataclass
class FoldResult:
    fold:          int
    test_season:   int
    train_seasons: list[int]
    predictions:   pd.DataFrame       # per-game predictions (spec output contract)
    feature_importance: pd.DataFrame  # from this fold's model
    wins:    int = 0
    losses:  int = 0
    pushes:  int = 0
    n_games: int = 0
    hit_rate: float = float("nan")
    model_log_loss:    float = float("nan")
    baseline_wins:   int = 0
    baseline_losses: int = 0
    baseline_hit_rate: float = float("nan")


@dataclass
class BacktestResult:
    experiment_id: str
    name:          str
    folds:         list[FoldResult] = field(default_factory=list)

    # Aggregated over all folds
    total_wins:    int = 0
    total_losses:  int = 0
    total_pushes:  int = 0
    total_n_games: int = 0
    overall_hit_rate: float = float("nan")
    gate_passed:   bool = False

    baseline_total_wins:   int = 0
    baseline_total_losses: int = 0
    baseline_hit_rate:     float = float("nan")

    # Feature importance averaged across folds
    avg_feature_importance: Optional[pd.DataFrame] = None
    feature_importance_dict: Optional[dict] = None

    def per_season_table(self) -> pd.DataFrame:
        rows = []
        for fr in self.folds:
            rows.append({
                "test_season": fr.test_season,
                "W":  fr.wins,
                "L":  fr.losses,
                "P":  fr.pushes,
                "hit_rate": fr.hit_rate,
                "n_games":  fr.n_games,
                "model_log_loss": fr.model_log_loss,
                "baseline_hit_rate": fr.baseline_hit_rate,
            })
        return pd.DataFrame(rows)

    def all_predictions(self) -> pd.DataFrame:
        return pd.concat([fr.predictions for fr in self.folds], ignore_index=True)


# ── Core scoring logic ───────────────────────────────────────────────────────

def _score_predictions(test_df: pd.DataFrame, probs: np.ndarray) -> pd.DataFrame:
    """
    Build the per-game prediction DataFrame per the output contract in
    MODELING_SPEC_PHASE1.md.

    Columns:
      game_id, season, week, home_team, away_team,
      home_spread_close, predicted_home_cover_prob, predicted_side,
      actual_home_covered, correct, ol_mismatch_flag

    ol_mismatch_flag is read from test_df if present (set to 0 if column missing,
    meaning the mismatch computation has not been run yet).
    """
    src_cols = ["game_id", "season", "week", "home_team", "away_team",
                "home_spread_close", "home_covered"]
    if "ol_mismatch_flag" in test_df.columns:
        src_cols.append("ol_mismatch_flag")

    out = test_df[src_cols].copy()

    out["predicted_home_cover_prob"] = probs
    out["predicted_side"] = np.where(probs > 0.5, "home", "away")
    out["actual_home_covered"] = out["home_covered"]   # keep original name for clarity

    def _correct(row) -> Optional[int]:
        if pd.isna(row["home_covered"]):
            return None                              # push
        pred_home = row["predicted_side"] == "home"
        return int(pred_home == row["home_covered"])

    out["correct"] = out.apply(_correct, axis=1)

    # ol_mismatch_flag: carry through from test_df if computed, else default 0
    if "ol_mismatch_flag" not in out.columns:
        out["ol_mismatch_flag"] = 0

    out = out.drop(columns=["home_covered"])
    return out


def _compute_fold_metrics(
    pred_df: pd.DataFrame,
    y_true: pd.Series,
    probs: np.ndarray,
) -> tuple[int, int, int, float, float]:
    """
    Returns (wins, losses, pushes, hit_rate, model_log_loss).
    """
    decided = pred_df.dropna(subset=["correct"])
    wins   = int(decided["correct"].sum())
    losses = int(len(decided) - wins)
    pushes = int(pred_df["actual_home_covered"].isna().sum())
    n      = wins + losses
    hit_rate = wins / n if n > 0 else float("nan")

    # Log-loss computed only on decided games
    valid_mask = ~y_true.isna()
    if valid_mask.sum() > 0:
        y_valid  = y_true[valid_mask].astype(int).values
        p_valid  = probs[valid_mask.values]
        p_clipped = np.clip(p_valid, 1e-7, 1 - 1e-7)
        ll = log_loss(y_valid, p_clipped)
    else:
        ll = float("nan")

    return wins, losses, pushes, hit_rate, ll


# ── Main walk-forward function ────────────────────────────────────────────────

def run_walk_forward(
    game_features: pd.DataFrame,
    experiment_id: str,
    name: str = "ol_xgb_v1",
    model_features: list | None = None,
    model_class=None,
    folds_override: list[tuple[list[int], int]] | None = None,
    gate_hit_rate: float = PHASE2_GATE_HIT_RATE,
    gate_min_games: int = PHASE2_GATE_MIN_GAMES,
) -> BacktestResult:
    """
    Run the walk-forward backtest.

    Parameters
    ----------
    game_features   : DataFrame from build_game_feature_matrix()
                      Must include the model feature columns + home_covered + game metadata
    experiment_id   : UUID string generated by the caller
    name            : human-readable experiment name
    model_features  : list of feature column names to use.
                      Defaults to ALL_MODEL_FEATURES (v1 feature set) for backward compat.
    model_class     : model class to instantiate each fold (must expose .fit() / .predict_proba()).
                      Defaults to OLXGBModel.
    folds_override  : Explicit fold list [(train_seasons, test_season), ...].
                      When None, falls back to the hardcoded FOLDS constant (Phase 1 behaviour).
    gate_hit_rate   : Hit-rate threshold for gate_passed evaluation.
    gate_min_games  : Minimum evaluated games for gate_passed evaluation.

    Returns
    -------
    BacktestResult with per-fold predictions, metrics, and feature importances
    """
    feature_cols  = model_features if model_features is not None else ALL_MODEL_FEATURES
    _model_class  = model_class    if model_class    is not None else OLXGBModel
    active_folds  = folds_override if folds_override is not None else FOLDS
    n_folds       = len(active_folds)

    result = BacktestResult(experiment_id=experiment_id, name=name)
    baseline = AlwaysHomeBaseline()
    all_importances = []

    for fold_num, (train_seasons, test_season) in enumerate(active_folds, start=1):
        logger.info(
            f"\n-- Fold {fold_num}/{n_folds} --  "
            f"train {train_seasons[0]}-{train_seasons[-1]}, test {test_season}"
        )

        train_mask = game_features["season"].isin(train_seasons)
        test_mask  = game_features["season"] == test_season

        train_df = game_features[train_mask].copy()
        test_df  = game_features[test_mask].copy()

        # Drop rows with null target from TRAINING (pushes cannot be trained on)
        train_df = train_df.dropna(subset=["home_covered"])

        X_train = train_df[feature_cols]
        y_train = train_df["home_covered"].astype(int)
        X_test  = test_df[feature_cols]
        y_test  = test_df["home_covered"]   # keep nulls (pushes) for scoring

        logger.info(
            f"  Training games: {len(train_df):,} | Test games: {len(test_df):,} "
            f"(of which {y_test.isna().sum()} are pushes)"
        )

        # ── Fit model ──────────────────────────────────────────────────────
        model = _model_class()
        model.fit(X_train, y_train)

        # ── Predict ────────────────────────────────────────────────────────
        probs = model.predict_proba(X_test)

        # ── Score ──────────────────────────────────────────────────────────
        pred_df = _score_predictions(test_df, probs)
        pred_df["fold"] = fold_num

        wins, losses, pushes, hit_rate, ll = _compute_fold_metrics(pred_df, y_test, probs)

        # ── Baseline ───────────────────────────────────────────────────────
        b_record = baseline.ats_record(test_df)

        # ── Feature importance ─────────────────────────────────────────────
        fi = model.feature_importance()
        fi["fold"] = fold_num
        all_importances.append(fi)

        fold_result = FoldResult(
            fold=fold_num,
            test_season=test_season,
            train_seasons=train_seasons,
            predictions=pred_df,
            feature_importance=fi,
            wins=wins,
            losses=losses,
            pushes=pushes,
            n_games=wins + losses,
            hit_rate=hit_rate,
            model_log_loss=ll,
            baseline_wins=b_record["wins"],
            baseline_losses=b_record["losses"],
            baseline_hit_rate=b_record["hit_rate"],
        )

        logger.info(
            f"  Model ATS:    {wins}-{losses}-{pushes}  ({hit_rate:.3%})  "
            f"log-loss={ll:.4f}"
        )
        logger.info(
            f"  Baseline ATS: {b_record['wins']}-{b_record['losses']}-{b_record['pushes']}  "
            f"({b_record['hit_rate']:.3%})"
        )

        result.folds.append(fold_result)

    # ── Aggregate results ─────────────────────────────────────────────────────
    result.total_wins   = sum(f.wins   for f in result.folds)
    result.total_losses = sum(f.losses for f in result.folds)
    result.total_pushes = sum(f.pushes for f in result.folds)
    result.total_n_games = result.total_wins + result.total_losses
    result.overall_hit_rate = (
        result.total_wins / result.total_n_games
        if result.total_n_games > 0 else float("nan")
    )
    result.gate_passed = (
        result.overall_hit_rate >= gate_hit_rate
        and result.total_n_games >= gate_min_games
    )

    result.baseline_total_wins   = sum(f.baseline_wins   for f in result.folds)
    result.baseline_total_losses = sum(f.baseline_losses for f in result.folds)
    b_n = result.baseline_total_wins + result.baseline_total_losses
    result.baseline_hit_rate = (
        result.baseline_total_wins / b_n if b_n > 0 else float("nan")
    )

    # Average feature importance across folds
    all_fi = pd.concat(all_importances)
    fi_df = (
        all_fi.groupby("feature")["importance"]
        .mean()
        .reset_index()
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    result.avg_feature_importance = fi_df

    # Also store as a dict for BigQuery serialization (feature_name → mean importance)
    result.feature_importance_dict = dict(zip(fi_df["feature"], fi_df["importance"]))

    logger.info(
        f"\n=== Final ATS: {result.total_wins}-{result.total_losses}-{result.total_pushes} "
        f"({result.overall_hit_rate:.3%}) over {result.total_n_games} games ==="
    )
    logger.info(
        f"Phase 2 gate (>=54%%, >=250 games): {'PASSED' if result.gate_passed else 'NOT MET'}"
    )

    return result


# ── Report generation ─────────────────────────────────────────────────────────

def format_backtest_report(result: BacktestResult) -> str:
    """
    Render a human-readable Markdown summary of the backtest result.
    This is the primary artifact delivered to PROJECT-LEAD.
    """
    lines = []
    lines.append(f"# Phase 1 Backtest Report")
    lines.append(f"")
    lines.append(f"**Experiment ID:** `{result.experiment_id}`")
    lines.append(f"**Name:** {result.name}")
    lines.append(f"")

    # ── 1. Methodology ────────────────────────────────────────────────────
    lines.append("## 1. Methodology")
    lines.append("")
    lines.append("**Walk-forward structure:**")
    lines.append("")
    lines.append("| Fold | Train seasons | Test season |")
    lines.append("|------|--------------|-------------|")
    for i, (train, test) in enumerate(FOLDS, 1):
        lines.append(f"| {i} | {train[0]}–{train[-1]} | {test} |")
    lines.append("")
    lines.append(f"**Model:** XGBoost classifier (`{result.name}`)")
    lines.append("")
    lines.append("**Features used:** see Section 5 feature importance table for complete list.")
    lines.append("")
    lines.append("**Week 1 cold-start:** Prior season's full-season average substituted for Week 1 features.")
    lines.append("2015 Week 1 (no prior season): league-wide 2015 average used. These games appear only in training folds.")
    lines.append("")
    lines.append("**Pushes:** Excluded from ATS hit-rate denominator (stored as NULL in `correct` column).")
    lines.append("")
    lines.append("**Scaling/imputation:** StandardScaler + mean imputer fit on training games only, applied to test.")
    lines.append("")

    # ── 2. Primary result ────────────────────────────────────────────────
    lines.append("## 2. Primary Result")
    lines.append("")
    lines.append(f"Overall ATS: **{result.total_wins}-{result.total_losses}-{result.total_pushes}**")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Hit rate | **{result.overall_hit_rate:.3%}** |")
    lines.append(f"| Sample size (W+L) | {result.total_n_games:,} |")
    lines.append(f"| Phase 2 gate (≥54%, ≥250 games) | {'**YES ✅**' if result.gate_passed else '**NO ❌**'} |")
    lines.append("")

    # ── 3. Per-season breakdown ───────────────────────────────────────────
    lines.append("## 3. Per-Season Breakdown")
    lines.append("")
    lines.append("| Test season | W | L | P | Hit rate | Log-loss | Baseline hit rate |")
    lines.append("|------------|---|---|---|----------|----------|-------------------|")
    for fr in result.folds:
        hr   = f"{fr.hit_rate:.3%}" if not np.isnan(fr.hit_rate) else "—"
        ll   = f"{fr.model_log_loss:.4f}" if not np.isnan(fr.model_log_loss) else "—"
        bhr  = f"{fr.baseline_hit_rate:.3%}" if not np.isnan(fr.baseline_hit_rate) else "—"
        lines.append(
            f"| {fr.test_season} | {fr.wins} | {fr.losses} | {fr.pushes} "
            f"| {hr} | {ll} | {bhr} |"
        )
    lines.append("")

    # ── 4. OL mismatch subset ─────────────────────────────────────────────
    lines.append("## 4. OL Mismatch Subset")
    lines.append("")

    all_preds = result.all_predictions()
    has_flags = "ol_mismatch_flag" in all_preds.columns and (all_preds["ol_mismatch_flag"] > 0).any()

    if not has_flags:
        lines.append("> `ol_mismatch_flag` is 0 for all predictions — mismatch computation not yet run.")
        lines.append("")
    else:
        from features.mismatch import subset_ats_record

        lines.append(
            "**Composite definition (approved 2026-05-03):**  "
            "`ol_composite = Z(ol_pass_epa_per_att) − Z(ol_pressure_proxy_rate)` (offense);  "
            "`def_composite = Z(def_pressure_proxy_rate) − Z(def_pass_epa_allowed_per_att)` (defense).  "
            "Quartiles computed per-season, expanding through each week."
        )
        lines.append("")
        lines.append(
            "**Flag = 1** — home team top-quartile OL offense AND away team bottom-quartile defense.  "
            "**Flag = 2** — away team top-quartile OL offense AND home team bottom-quartile defense."
        )
        lines.append("")
        lines.append("**Reminder:** subset result is diagnostic only — it does not gate Phase 2.")
        lines.append("")

        for fv in [1, 2]:
            rec = subset_ats_record(all_preds, flag_value=fv)
            label = (
                "Flag=1 (home elite OL vs. weak away D)"
                if fv == 1
                else "Flag=2 (away elite OL vs. weak home D)"
            )
            hr_str = f"{rec['hit_rate']:.3%}" if rec["hit_rate"] == rec["hit_rate"] else "—"
            lines.append(f"### {label}")
            lines.append("")
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| ATS record | {rec['wins']}-{rec['losses']}-{rec['pushes']} |")
            lines.append(f"| Hit rate | **{hr_str}** |")
            lines.append(f"| Sample size (W+L) | {rec['n_games']} |")
            full_hr_str = f"{result.overall_hit_rate:.3%}" if result.overall_hit_rate == result.overall_hit_rate else "—"
            lines.append(f"| Full-universe hit rate (for comparison) | {full_hr_str} |")
            lines.append("")
            if rec["n_games"] < 50:
                lines.append(
                    f"> ⚠️ Sample size is small ({rec['n_games']} games). "
                    "Do not draw strong conclusions from this subset."
                )
                lines.append("")

    # ── 5. Feature importance ─────────────────────────────────────────────
    lines.append("## 5. Feature Importance (avg gain across 6 folds)")
    lines.append("")
    lines.append("| Rank | Feature | Avg importance |")
    lines.append("|------|---------|---------------|")
    if result.avg_feature_importance is not None:
        for i, row in result.avg_feature_importance.head(20).iterrows():
            lines.append(f"| {i+1} | `{row['feature']}` | {row['importance']:.4f} |")
    lines.append("")

    # ── 6. Null baseline comparison ───────────────────────────────────────
    lines.append("## 6. Null Baseline Comparison (always-home)")
    lines.append("")
    lines.append("| | W | L | P | Hit rate |")
    lines.append("|-|---|---|---|----------|")
    lines.append(
        f"| Model | {result.total_wins} | {result.total_losses} | {result.total_pushes} "
        f"| {result.overall_hit_rate:.3%} |"
    )
    b_n = result.baseline_total_wins + result.baseline_total_losses
    b_p = result.total_n_games + result.total_pushes - b_n  # approx pushes for baseline
    lines.append(
        f"| Always-home baseline | {result.baseline_total_wins} | {result.baseline_total_losses} "
        f"| — | {result.baseline_hit_rate:.3%} |"
    )
    lines.append("")

    # ── 7. Notes ──────────────────────────────────────────────────────────
    lines.append("## 7. Notes / Observations")
    lines.append("")
    lines.append("_To be completed by MODELING after reviewing results._")
    lines.append("")
    lines.append("Suggested items to address:")
    lines.append("- Which features ranked highest and whether that aligns with the OL hypothesis")
    lines.append("- Whether any season (fold) was an outlier")
    lines.append("- Data quality issues encountered beyond what the pipeline validation caught")
    lines.append("- What to try next if gate is not met")
    lines.append("")

    return "\n".join(lines)

# MODELING Spec — Phase 1

**Owner:** PROJECT-LEAD
**Consumer:** MODELING (implements), PROJECT-LEAD (reviews artifact)
**Last updated:** 2026-05-03
**Status:** Active — Phase 1

---

## Purpose

This spec defines what MODELING must build and deliver for Phase 1. The deliverable is a reproducible backtest artifact that either greenlights Phase 2 or doesn't. MODELING does not write API code, does not build current-week prediction pipelines, and does not productionize anything in Phase 1.

**Reads from:** `curated.games`, `curated.plays` (BigQuery, project `nfl-model-471509`)
**Writes to:** `experiments.backtest_runs`, `experiments.backtest_predictions` (BigQuery)
**Deliverable:** Reproducible backtest notebook + written result summary

---

## Phase 2 Gate (reminder)

**Primary:** ≥ 54% ATS hit rate vs. closing line on ≥ 250 out-of-sample games (flat bet)
**Secondary:** ATS hit rate within the OL mismatch subset (diagnostic only — does not block or unlock the gate)

Both are reported in the backtest artifact. Only the primary determines go/no-go.

---

## Walk-Forward Methodology

This is non-negotiable. Do not deviate from this structure.

- **Training window:** 4 seasons
- **Test window:** 1 season (completely held out — no leakage of any kind)
- **Folds:**

| Fold | Train seasons | Test season |
|------|--------------|-------------|
| 1 | 2015–2018 | 2019 |
| 2 | 2016–2019 | 2020 |
| 3 | 2017–2020 | 2021 |
| 4 | 2018–2021 | 2022 |
| 5 | 2019–2022 | 2023 |
| 6 | 2020–2023 | 2024 |

2025 is the current season and is **not used as a test fold** in Phase 1. It may be used as the final training season in a prospective model after the gate is cleared, but not for backtest evaluation.

**Leakage rules:**
- Features must be computable using only data available before the test season begins
- Closing spreads (`home_spread_close`) are used only as the outcome label, never as a predictor feature
- No look-ahead normalization: any scaling or normalization is fit on the training set only, applied to test

---

## Feature Set — v2 (Comprehensive nflfastR)

**Updated 2026-05-03 per ADR-005.** The model is a comprehensive NFL game predictor. OL metrics are one component. All features are derived from `curated.plays` and `curated.games` — nflfastR only, no licensed sources.

Features are computed at the **team-season level** (rolling season-to-date through the prior week) and joined to each game. The unit of prediction is one game. All rolling features carry a `home_` or `away_` prefix reflecting which team they describe from the home team's perspective.

---

### QB / Passing Efficiency (per team, season-to-date)

| Feature name | Definition | Source columns |
|---|---|---|
| `qb_epa_per_dropback` | EPA per dropback (pass attempts + sacks + scrambles) | `epa`, `play_type='pass'` + sack plays, `posteam` |
| `qb_cpoe` | Mean completion % over expected on pass attempts | `cpoe`, `play_type='pass'`, `posteam` |
| `qb_epa_under_pressure` | Mean EPA on plays where QB was hit or sacked | `epa`, `qb_hit=TRUE OR sack=TRUE`, `posteam` |
| `pass_explosive_rate` | % of pass plays gaining ≥20 air+YAC yards | `yards_gained >= 20`, `play_type='pass'`, `posteam` |

---

### OL / Pass-Blocking (per team, season-to-date)

| Feature name | Definition | Source columns |
|---|---|---|
| `ol_sack_rate` | Sacks allowed / pass attempts | `sack`, `play_type='pass'`, `posteam` |
| `ol_qb_hit_rate` | QB hits / pass attempts | `qb_hit`, `play_type='pass'`, `posteam` |
| `ol_pressure_proxy_rate` | (Sacks + QB hits) / pass attempts | Combined above |
| `ol_pass_epa_per_att` | Mean EPA on pass attempts | `epa`, `play_type='pass'`, `posteam` |

---

### OL / Run-Blocking (per team, season-to-date)

| Feature name | Definition | Source columns |
|---|---|---|
| `ol_rush_epa_per_att` | Mean EPA on rush attempts | `epa`, `play_type='run'`, `posteam` |
| `ol_rush_yards_per_att` | Mean yards gained on rush attempts | `yards_gained`, `play_type='run'`, `posteam` |
| `rush_explosive_rate` | % of rush plays gaining ≥10 yards | `yards_gained >= 10`, `play_type='run'`, `posteam` |

---

### Defense (per team, season-to-date — from defteam perspective)

Mirrors the offensive metrics above. These measure what the defense allows and generates.

| Feature name | Definition |
|---|---|
| `def_epa_per_play` | Mean EPA allowed per play (all play types) |
| `def_pass_epa_allowed_per_att` | Mean EPA allowed on pass attempts |
| `def_rush_epa_allowed_per_att` | Mean EPA allowed on rush attempts |
| `def_pressure_proxy_rate` | (Sacks + QB hits generated) / opponent pass attempts |
| `def_sack_rate` | Sacks generated / opponent pass attempts |
| `def_explosive_pass_allowed_rate` | % of opponent pass plays allowing ≥20 yards |
| `def_explosive_rush_allowed_rate` | % of opponent rush plays allowing ≥10 yards |

---

### Situational / Form Features (per team, from schedules + game results)

| Feature name | Definition | Source |
|---|---|---|
| `rest_days` | Days since last game (or 14 for post-bye) | `curated.games.game_date` |
| `rest_differential` | home_rest_days − away_rest_days | Derived |
| `prior_week_margin` | Score margin in most recent game (positive = won) | `curated.games` rolling |
| `rolling_3wk_epa_trend` | Mean team EPA per play over the last 3 games | `curated.plays` rolling |
| `season_win_pct` | Season-to-date win % | `curated.games` rolling |

---

### Game-Level Context Features

| Feature name | Definition | Source |
|---|---|---|
| `home_advantage` | 1 = home team, 0 = away | `curated.games` |
| `div_game` | Divisional matchup flag | `curated.games.div_game` |
| `roof_dome` | 1 if dome/retractable closed, 0 otherwise | `curated.games.roof` |
| `temp` | Game-time temperature °F; default 70 for dome games | `curated.games.temp` |
| `wind` | Wind speed mph; default 0 for dome games | `curated.games.wind` |

---

### Feature Engineering Notes

- All rolling features use season-to-date data through week W-1 only — no same-week or future data.
- Week 1 cold-start: use prior season's full-season average. Document this in the artifact.
- Minimum sample threshold: ≥20 qualifying plays before computing a rate. Below threshold: use league-average for that season-week. Flag but do not drop the game.
- Features are named by what they measure, not by data source.
- The home/away prefix refers to which team occupies that role in the game being predicted — every feature appears twice in the model (once for each team).

---

## OL Mismatch Subset

The OL mismatch subset definition was approved in `experiments/OL_COMPOSITE_PROPOSAL.md` (approved 2026-05-03 with one correction applied). That definition carries forward unchanged into v2. The `ol_mismatch_flag` logic in `features/mismatch.py` is already correct — no changes needed.

---

## Model Requirements

MODELING chooses the model architecture. The output contract is fixed regardless of what model is used.

**Output contract — per game, per fold:**
- `game_id` — nflfastR game ID
- `season` — test season
- `fold` — fold number (1–6)
- `home_team`, `away_team`
- `home_spread_close` — closing spread (from `curated.games`, home perspective)
- `predicted_home_cover_prob` — model probability that home team covers the closing spread (0..1)
- `predicted_side` — "home" if `predicted_home_cover_prob > 0.5`, else "away"
- `actual_home_covered` — from `curated.games.home_covered` (ground truth)
- `correct` — 1 if `predicted_side` matches actual result, 0 if not, NULL if push
- `ol_mismatch_flag` — 1 if this game is in the OL mismatch subset (after approval), else 0

Write all predictions to `experiments.backtest_predictions` (schema below).

**Baseline model (required):** Also run a naive baseline — always predict the home team covers — and record its ATS record alongside the model's. This is the null comparison required by the backtest artifact spec.

---

## BigQuery Output Schemas

### `experiments.backtest_runs`

One row per experiment run (a full 6-fold backtest execution).

| Column | Type | Notes |
|--------|------|-------|
| `experiment_id` | STRING | UUID, generated at run time |
| `name` | STRING | Human-readable, e.g. `ol_xgb_v1` |
| `run_at` | TIMESTAMP | When the backtest was executed |
| `model_type` | STRING | e.g. `xgboost`, `logistic_regression` |
| `features` | JSON | List of feature names used |
| `training_window_years` | INT64 | 4 |
| `seasons_evaluated` | JSON | List of test seasons |
| `ats_record_wins` | INT64 | Total correct predictions |
| `ats_record_losses` | INT64 | Total incorrect predictions |
| `ats_record_pushes` | INT64 | Total pushes (excluded from hit rate) |
| `ats_hit_rate` | FLOAT64 | wins / (wins + losses) |
| `n_games_evaluated` | INT64 | wins + losses (pushes excluded) |
| `gate_passed` | BOOL | TRUE if hit_rate ≥ 0.54 AND n_games ≥ 250 |
| `notes` | STRING | Free text — what changed, what was tried |

### `experiments.backtest_predictions`

One row per game per fold.

| Column | Type | Notes |
|--------|------|-------|
| `experiment_id` | STRING | FK → backtest_runs |
| `fold` | INT64 | 1–6 |
| `game_id` | STRING | |
| `season` | INT64 | Test season |
| `week` | INT64 | |
| `home_team` | STRING | |
| `away_team` | STRING | |
| `home_spread_close` | FLOAT64 | |
| `predicted_home_cover_prob` | FLOAT64 | |
| `predicted_side` | STRING | "home" or "away" |
| `actual_home_covered` | BOOL | NULL on push |
| `correct` | INT64 | 1, 0, or NULL (push) |
| `ol_mismatch_flag` | INT64 | 1 or 0 (0 until subset approved) |

Partitioned by `season`.

---

## Backtest Artifact — Required Contents

The artifact is a Jupyter notebook (or equivalent reproducible script) that produces all numbers from scratch by querying BigQuery. Running it end-to-end must reproduce the same results.

The artifact must contain:

**1. Methodology section**
- Walk-forward structure (fold table above)
- Feature list used
- Model type and key hyperparameters
- How Week 1 cold-start was handled
- How pushes are treated

**2. Primary result**
- Overall ATS record (W-L-P) across all folds
- Hit rate (W / (W+L))
- Sample size (W+L)
- Whether the Phase 2 gate is met: YES or NO

**3. Per-season breakdown**

| Test season | W | L | P | Hit rate |
|------------|---|---|---|----------|
| 2019 | | | | |
| 2020 | | | | |
| ... | | | | |

**4. Secondary result (after OL mismatch approval)**
- OL mismatch subset: total games, ATS record, hit rate
- Comparison to full-universe result

**5. Feature importance**
- Ranked list of features by contribution (SHAP values, permutation importance, or model-native importance — MODELING's choice, but document which method)

**6. Null baseline comparison**
- Always-home ATS record on the same game set
- Demonstrates the model adds lift beyond the home field baseline

**7. Notes / observations**
- What worked, what surprised you, what you'd try next
- Any data quality issues encountered that weren't caught in validation

---

## What Is Out of Scope for Phase 1

- Current-week prediction pipeline (no live or prospective predictions)
- Model serving or API integration
- Ensembling multiple models (run one clean model first)
- Hyperparameter search beyond a reasonable first pass (don't over-optimize before the gate)
- FTN, NGS, SIS, or PFF features
- Totals or player prop models
- Bankroll simulation or Kelly sizing

---

## Sequence

1. Read this spec and `docs/PIPELINE_SPEC_PHASE1.md` for data context
2. Verify you can query `curated.games` and `curated.plays` in BigQuery
3. Build feature computation logic (season-to-date rolling averages per team per week)
4. Implement walk-forward scaffold (6 folds, strict train/test split)
5. Run first pass — produce raw numbers, don't over-tune
6. **Submit OL composite definition to PROJECT-LEAD for approval before running subset analysis**
7. Refine model on first-pass learnings
8. Run final backtest with approved OL mismatch flag
9. Produce complete artifact per the spec above
10. Write results to `experiments.backtest_runs` and `experiments.backtest_predictions`
11. Share artifact with PROJECT-LEAD for gate review

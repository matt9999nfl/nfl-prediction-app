# Phase 4 — Model Validation Spec

**Phase:** 4 — Validation & Improvements  
**Author:** PROJECT-LEAD  
**Date:** 2026-05-16  
**Status:** ⏳ PLANNING — not started; awaiting project owner approval  
**Tracking:** `PHASE4_STATUS.md` (Track 1 + Track 2 rows)

This document specifies the investigation required to determine whether the rushing-feature experiment result is legitimate, and the exact code changes the runner needs before that investigation can run. It is the detailed spec behind the high-level Track 1 and Track 2 rows in `PHASE4_STATUS.md`. MODELING reads this document in full before starting any work.

---

## Why This Exists

Three experiments (test1, test2, test3) using 10 rushing features reported 58–61% ATS over a walk-forward backtest. That result directly contradicts the May 3 gate review, which found 49.65% ATS on the same walk-forward harness with 52 features. A +9 percentage-point gain from removing 42 features is large enough to demand verification — at -110 odds, a genuine 58% hit rate represents roughly 11% ROI per bet, which would be among the best-documented edges in NFL betting history. That kind of claim requires strong evidence.

Only test3 is a legitimate multi-fold result (6 folds, 1,591 games). test1 and test2 are single-fold runs on ~260 games each and should be ignored.

The investigation has three tiers. Tier 1 answers "is the harness trustworthy?" and takes one MODELING session. PROJECT-LEAD makes a Go/No-Go before Tier 2 begins. Tier 3 is pre-production due diligence only if Tier 2 passes.

Two code changes (configurable seed, shuffle-labels mode) must be made before Tier 1 can run. The runner currently hardcodes `random_state=42` and has no leakage-testing capability. Those changes are part of Phase 4 Track 2 and are specified in Part B of this document.

---

## Part A — Validation Investigation

### Tier 1 — "Is the harness trustworthy?" (one MODELING session)

#### A1 — Per-fold breakdown for test3

**What:** Query `experiments.backtest_predictions` for the test3 `run_id`. Group by `season`, compute `wins / (wins + losses)`. Record the per-season table.

```sql
SELECT
  season,
  COUNTIF(correct = 1)                                            AS wins,
  COUNTIF(correct = 0)                                            AS losses,
  COUNTIF(correct IS NULL)                                        AS pushes,
  SAFE_DIVIDE(COUNTIF(correct = 1), COUNTIF(correct IS NOT NULL)) AS hit_rate,
  COUNTIF(correct IS NOT NULL)                                    AS n_games
FROM `nfl-model-471509.experiments.backtest_predictions`
WHERE run_id = '<test3_run_id>'
GROUP BY season
ORDER BY season
```

**Decision rule:**
- One fold >65% and the other five average <53% → signal is concentrated in one lucky season. Classify as noise. Do not proceed to Tier 2.
- All six folds between 54–63% → signal is distributed. Continue to A2.
- Mixed but ≥4 folds above 54% → continue to A2, flag as fragile.

---

#### A2 — Reproduce the 52-feature v2 result through the config-driven runner

**What:** Create a new experiment config listing all 52 v2 curated features with the same fold structure as test3 (start_season=2016, end_season=2025, train_seasons=4). Run it through `run_experiment.py`. Compare the hit rate against the May 3 standalone result of 49.65%.

**52 feature list** (base per-team names; runner auto-adds home_/away_ prefixes):

From `ALL_TEAM_RATE_FEATURES` (`features/ol_metrics.py`):
`ol_rush_epa_per_att`, `ol_rush_yards_per_att`, `ol_first_down_rush_rate`, `ol_sack_rate`, `ol_pass_epa_per_att`, `ol_pressure_proxy_rate`, `def_rush_epa_allowed_per_att`, `def_rush_yards_allowed_per_att`, `def_first_down_rush_rate_allowed`, `def_sack_rate`, `def_pass_epa_allowed_per_att`, `def_pressure_proxy_rate`

From `ALL_ADDITIONAL_TEAM_FEATURES` (`features/comprehensive.py`):
`qb_epa_per_dropback`, `pass_explosive_rate`, `rush_explosive_rate`, `def_epa_per_play`, `turnover_rate`, `season_win_pct`, `rolling_3wk_epa_trend`, `third_down_conv_rate`

From `SITUATIONAL_TEAM_FEATURES` (`features/situational.py`):
`rest_days`, `is_home_field_advantage`, `back_to_back_flag`

**Decision rule:**
- New runner produces ≈49.65% (within ±1 pp) → runner is faithful to the old standalone script. The rush-only result is genuinely from feature selection. Continue to A3.
- New runner produces a materially different result (≥51% or ≤48%) → there is a bug in the config-driven path. **Stop. Find and fix the bug. Do not trust any experiment result from the new runner until it reproduces 49.65%.** This supersedes everything else in the investigation.

---

#### A3 — Shuffled-label leakage test

**What:** Re-run the test3 config (10 rushing features, 2016–2025, train=4) with `shuffle_labels: true` in the methodology block. This requires Part B item B2 (shuffle-labels mode) to be implemented first. Record the hit rate.

**Expected result if no leakage:** ≈50%. Randomly shuffled labels → model learns noise → random predictions → ~50% ATS.

**Decision rule:**
- Hit rate ≥54% on shuffled labels → leakage detected somewhere in the pipeline. **Stop. Begin leakage bisection** (strip feature groups one at a time and rerun the shuffled test until the hit rate falls to ~50%). The 58.3% real-label result is discarded pending a clean bill of health.
- Hit rate ≤52% → leakage ruled out. The 58.3% on real labels is genuine model output. Continue to Tier 2.
- Hit rate 52–54% → borderline. Re-run with 3 additional seeds to average out noise. If the mean across seeds is <53%, proceed to Tier 2 with a caution flag.

---

### Tier 1 Go/No-Go

Before MODELING starts Tier 2, all three conditions must hold:
1. Per-fold breakdown shows signal in multiple folds, not concentrated in one.
2. 52-feature reproduction returns ≈49.65% (runner is faithful).
3. Shuffled-label hit rate is ≤52% (no leakage).

MODELING records the Tier 1 results in the table at the bottom of this document and notifies PROJECT-LEAD. PROJECT-LEAD makes the Go/No-Go call.

---

### Tier 2 — "Is the signal stable and broad?" (second MODELING session)

*Locked until PROJECT-LEAD confirms Tier 1 Go.*

#### A4 — Seed stability

**What:** Re-run the test3 config with `random_seed` set to 1, 7, 99, 314, and 2024. Requires Part B item B1. Record the hit rate for each seed.

**Decision rule:**
- Max − Min across all 6 seeds (including original seed 42: 58.3%) ≤ 2 pp → seed-stable signal. Proceed.
- Max − Min > 5 pp → the 58.3% is partly a seed-lottery effect. Flag prominently. The model is not robust enough for production use without seed averaging.

---

#### A5 — 2025 out-of-sample holdout

**What:** Run a single-fold experiment: train on 2021–2024, test on 2025. The 2025 season was inside test3's F6 but was never examined or tuned against during the rush-feature exploration. Evaluate cold.

**Decision rule:**
- 2025 holdout hit rate ≥56% → the model generalises to genuinely unseen data. Strong positive signal.
- 2025 holdout hit rate ≤52% → prior results are partially in-sample artifacts from the exploration window. The hypothesis needs reframing.

---

#### A6 — Feature ablation

**What:** Three configs, same fold structure as test3. Record the hit rate for each.

| Config | Features |
|--------|----------|
| Rush-only | 10 rushing features (already have: 58.3%) |
| v2-only | 52 v2 features (result from A2: target ≈49.65%) |
| Union | All 52 v2 features — rush features are already included, so no new features added; this is the same as v2-only and should confirm A2 |

Then run one more config: the 42 non-rushing features from the v2 set only (v2 minus the rush features). This tells us whether the poor v2 result was because rushing features were being drowned out by noise from the other 42.

**Decision rule:**
- 42-non-rush-only hits ≈49% and rush-only hits 58% → the rush features contain real signal that the non-rush features diluted.
- 42-non-rush-only also hits ≥55% → the gain isn't specifically from rushing; it's from having any small feature set. The hypothesis needs to be about feature selection methodology, not specifically rushing.

---

#### A7 — Per-spread-size hit rate slice

**What:** Using `analyze_experiment.py` (Part B item B4), compute the test3 hit rate for four spread buckets: |spread| ≤3, (3, 7], (7, 10], >10.

**Decision rule:**
- Edge concentrated in |spread| > 10 only → known efficient-market quirk; blowout lines are set lazily. This is real but not tradeable at scale with reasonable bet sizing.
- Edge present across spread buckets including ≤7 → much more credible as a genuine and broadly applicable signal.

---

### Tier 2 Go/No-Go

PROJECT-LEAD reviews all Tier 2 results before Tier 3 begins. The specific decision criteria:

1. Seed stability ≤2 pp variance → Proceed.
2. 2025 holdout ≥54% → Proceed.
3. Feature ablation confirms rushing is the source of lift → Proceed.
4. Spread-size slice shows edge is not exclusively in large spreads → Proceed.

If all four pass: proceed to Tier 3 pre-production due diligence and a formal gate review.

---

### Tier 3 — Pre-production due diligence

*Locked until Tier 2 Go/No-Go confirmed.*

#### A8 — Calibration check

Using `analyze_experiment.py`, plot predicted P(home covers) in 10 bins vs actual cover rate. A genuine-edge model tracks the 45-degree diagonal (predicted 60% → actual 60%). A model exploiting a quirk often shows wild miscalibration in one bin.

#### A9 — Permutation feature importance

Using `analyze_experiment.py`, permute each of the 10 rushing features independently and measure the drop in hit rate. If a single feature accounts for >50% of the lift, the model is brittle and unlikely to survive line efficiency improvements or rule changes.

#### A10 — Formal gate review

If A8 and A9 are clean, PROJECT-LEAD writes a formal gate review document (following the same format as `GATE_REVIEW_PHASE1.md`). If the experiment passes the review, `gate_passed = true` is set on that experiment in `platform.experiment_configs` and the honest-evaluation banner in the FRONTEND is retired for that experiment.

---

## Part B — Code Changes Required

These changes are part of Phase 4 Track 2. They must be committed before the Track 1 investigation begins. All changes are in `02-MODELING/`. Nothing outside that directory is affected.

---

### B1 — Configurable `random_seed` in methodology config

**Required for:** A4 (seed stability).  
**Priority:** HIGH.

**Current state:** `random_state=42` is hardcoded in `XGB_PARAMS_V2` in `models/xgb_v2.py`. Every experiment run uses seed 42. There is no way to test seed stability without editing source code.

**Changes:**

`models/ol_xgb.py` — add `random_seed` parameter to `__init__`:
```python
def __init__(self, params=None, random_seed=42):
    p = dict(params or XGB_PARAMS)
    p["random_state"] = random_seed
    self.params = p
    # ... rest of init unchanged
```

`models/xgb_v2.py` — same pattern:
```python
def __init__(self, params=None, random_seed=42):
    p = dict(params or XGB_PARAMS_V2)
    p["random_state"] = random_seed
    super().__init__(params=p, random_seed=random_seed)
```

`backtests/walk_forward.py` — add `random_seed` param to `run_walk_forward()` and pass it to model instantiation inside the fold loop:
```python
def run_walk_forward(..., random_seed: int = 42) -> BacktestResult:
    ...
    # In the fold loop, line ~292:
    model = _model_class(random_seed=random_seed)
```

`backtests/run_experiment.py` — read seed from config and pass to `run_walk_forward`:
```python
random_seed = int(methodology.get("random_seed", 42))
...
result = run_walk_forward(
    ...
    random_seed=random_seed,
)
```

---

### B2 — Shuffle-labels mode for leakage detection

**Required for:** A3 (the gold-standard leakage test).  
**Priority:** HIGH.

**Current state:** No mechanism to shuffle `home_covered`. A leakage test is impossible without editing source code.

**Changes:**

`backtests/run_experiment.py` — after loading `games` (step 3), before building the feature matrix (step 4):

```python
shuffle_labels = bool(methodology.get("shuffle_labels", False))
if shuffle_labels:
    logger.warning(
        "SHUFFLE_LABELS=True — this is a leakage-detection run. "
        "home_covered will be randomly permuted within each season. "
        "gate_passed will be forced to False regardless of hit rate."
    )
    rng = np.random.default_rng(random_seed)
    for season in games["season"].unique():
        mask = games["season"] == season
        shuffled = rng.permutation(games.loc[mask, "home_covered"].values)
        games.loc[mask, "home_covered"] = shuffled
```

After the backtest completes, force `gate_passed = False` for shuffle runs:
```python
if shuffle_labels:
    gate_passed = False  # Never promote a shuffle-label run
```

When writing to BigQuery, append `"[SHUFFLE_LABELS=True]"` to the `notes` field so the run is permanently distinguishable in the database.

**Important:** The shuffle must happen at the `games` DataFrame level, before `build_feature_matrix` is called. Shuffling inside `run_walk_forward` would introduce state-sharing risk across folds.

---

### B3 — Per-fold breakdown query (no code change)

**Required for:** A1.  
**Priority:** HIGH.

No code change needed. A1 uses a direct BigQuery query (see the SQL in §A1). MODELING runs this immediately using the test3 `run_id`. The result can also be read from the local CSV artifact at `02-MODELING/backtests/reports/{run_id}_by_season.csv` if it was written during the test3 run.

---

### B4 — `analyze_experiment.py` standalone analysis script

**Required for:** A7 (spread slice), A8 (calibration), A9 (permutation importance).  
**Priority:** MEDIUM.

**New file:** `02-MODELING/backtests/analyze_experiment.py`

CLI interface:
```
python backtests/analyze_experiment.py --run_id <run_id> [--analyses spread,calibration,permutation]
```

Outputs (all written to `02-MODELING/backtests/reports/`):
- `{run_id}_per_spread_slice.csv` — hit rate by |spread| bucket (≤3, 3–7, 7–10, >10)
- `{run_id}_calibration.csv` — 10 equal-width bins of P(home covers) vs actual cover rate
- `{run_id}_permutation_importance.csv` — for each feature, the drop in hit rate when that feature is randomly permuted in the test set (averaged across folds)

For spread slice and calibration, the script only needs `experiments.backtest_predictions` from BigQuery — no model rerun.

For permutation importance, the script must rebuild the feature matrix and rerun fold-level inference. It should call `build_feature_matrix` and the model's `fit`/`predict_proba` directly — not re-trigger the full runner. This is a read-only analysis pass; it does not write to BigQuery.

---

### B5 — `compare_experiments.py` standalone comparison script

**Required for:** A6 (feature ablation comparison), general investigative use.  
**Priority:** MEDIUM.

**New file:** `02-MODELING/backtests/compare_experiments.py`

CLI interface:
```
python backtests/compare_experiments.py --run_ids <id1> <id2> [<id3> ...]
```

Outputs a Markdown table to stdout and writes to `02-MODELING/backtests/reports/{timestamp}_comparison.md`:

```
| Metric           | Experiment A       | Experiment B       |
|------------------|--------------------|--------------------|
| Name             | ...                | ...                |
| Overall hit rate | XX.X%              | XX.X%              |
| N games          | 1,591              | 1,557              |
| Gate passed      | No                 | No                 |
| Season 2020      | XX.X%              | XX.X%              |
| Season 2021      | XX.X%              | XX.X%              |
| ...              | ...                | ...                |
| Top feature 1    | feature_name       | feature_name       |
| Top feature 2    | ...                | ...                |
```

Sources: `experiments.backtest_runs` (aggregate metrics, feature importance JSON), `experiments.backtest_predictions` (per-season breakdown).

---

### B6 — 52-feature config for A2 (runner faithfulness check)

**Required for:** A2.  
**Priority:** HIGH.

No code change. MODELING creates a new experiment config via the dashboard or direct BQ INSERT into `platform.experiment_configs`:

```json
{
  "name": "v2-52-feature-faithfulness-check",
  "description": "Reproduce May-3 v2 result (49.65%) through config-driven runner. Runner faithfulness test. Phase 4 Track 1 A2.",
  "features": [
    {"dataset": "curated", "column": "ol_rush_epa_per_att",              "semantic_name": "ol_rush_epa_per_att"},
    {"dataset": "curated", "column": "ol_rush_yards_per_att",            "semantic_name": "ol_rush_yards_per_att"},
    {"dataset": "curated", "column": "ol_first_down_rush_rate",          "semantic_name": "ol_first_down_rush_rate"},
    {"dataset": "curated", "column": "ol_sack_rate",                     "semantic_name": "ol_sack_rate"},
    {"dataset": "curated", "column": "ol_pass_epa_per_att",              "semantic_name": "ol_pass_epa_per_att"},
    {"dataset": "curated", "column": "ol_pressure_proxy_rate",           "semantic_name": "ol_pressure_proxy_rate"},
    {"dataset": "curated", "column": "def_rush_epa_allowed_per_att",     "semantic_name": "def_rush_epa_allowed_per_att"},
    {"dataset": "curated", "column": "def_rush_yards_allowed_per_att",   "semantic_name": "def_rush_yards_allowed_per_att"},
    {"dataset": "curated", "column": "def_first_down_rush_rate_allowed", "semantic_name": "def_first_down_rush_rate_allowed"},
    {"dataset": "curated", "column": "def_sack_rate",                    "semantic_name": "def_sack_rate"},
    {"dataset": "curated", "column": "def_pass_epa_allowed_per_att",     "semantic_name": "def_pass_epa_allowed_per_att"},
    {"dataset": "curated", "column": "def_pressure_proxy_rate",          "semantic_name": "def_pressure_proxy_rate"},
    {"dataset": "curated", "column": "qb_epa_per_dropback",              "semantic_name": "qb_epa_per_dropback"},
    {"dataset": "curated", "column": "pass_explosive_rate",              "semantic_name": "pass_explosive_rate"},
    {"dataset": "curated", "column": "rush_explosive_rate",              "semantic_name": "rush_explosive_rate"},
    {"dataset": "curated", "column": "def_epa_per_play",                 "semantic_name": "def_epa_per_play"},
    {"dataset": "curated", "column": "turnover_rate",                    "semantic_name": "turnover_rate"},
    {"dataset": "curated", "column": "season_win_pct",                   "semantic_name": "season_win_pct"},
    {"dataset": "curated", "column": "rolling_3wk_epa_trend",            "semantic_name": "rolling_3wk_epa_trend"},
    {"dataset": "curated", "column": "third_down_conv_rate",             "semantic_name": "third_down_conv_rate"},
    {"dataset": "curated", "column": "rest_days",                        "semantic_name": "rest_days"},
    {"dataset": "curated", "column": "is_home_field_advantage",          "semantic_name": "is_home_field_advantage"},
    {"dataset": "curated", "column": "back_to_back_flag",                "semantic_name": "back_to_back_flag"}
  ],
  "methodology": {
    "start_season": 2016,
    "end_season": 2025,
    "train_seasons": 4,
    "test_seasons": 1,
    "random_seed": 42,
    "shuffle_labels": false
  },
  "model": {"type": "xgboost"},
  "evaluation": {
    "success_threshold": 0.54,
    "min_sample": 250,
    "metric": "ats_hit_rate"
  }
}
```

---

## Tier 1 Results

*Completed by MODELING — 2026-05-17 (post-INC-001-fix re-run)*

**Note:** The previous Tier 1 results (recorded 2026-05-17 in the same session) were run against inverted labels and are entirely invalid. The numbers below are the corrected results, re-run after DATA-PIPELINE rebuilt `curated.games` with the correct `home_covered` derivation. Spread-bin diagnostic confirmed all 5 buckets are 45–55% before any experiment was re-run.

**Summary (post-fix):** The label fix is confirmed clean. A2 shows the config-driven runner is faithful to the May 3 standalone result (50.19% vs target 49.65%). A3 shows no leakage (51.1% on shuffled labels). However, A1 reveals the rush-feature result is not real signal: with correct labels, test3 returns 48.8% overall and only 1 of 6 folds exceeds 54% (2021: 55.2%). The previous 58.3% headline was an artifact of the inverted labels, not a genuine model edge. Tier 1 is a NO-GO on signal grounds: the infrastructure is trustworthy, but the rushing-feature hypothesis does not hold up on correct data.

| Test | Result | Decision |
|------|--------|----------|
| A1 — Per-fold hit rates for test3 (run_id: `20260517_020637_245bc9`) | 1/6 folds above 54% (2021=55.2%); 5/6 below 52%. Season detail: 2020=46.5%, 2021=55.2%, 2022=48.3%, 2023=51.6%, 2024=47.0%, 2025=44.3%. Overall 48.8% (772-810-33). | ❌ Signal concentrated in one fold. Decision rule: "One fold >65% and others <53%" does not apply here, but "all six folds 54–63%" also does not apply. Only 1/6 above 54%, 5/6 below 52%. Classify as noise. |
| A2 — 23-feature faithfulness check (run_id: `20260517_020202_0504ff`) | 50.190% (794-788-33, 1,582 games). Per-season: 2020=52.3%, 2021=50.0%, 2022=52.5%, 2023=46.5%, 2024=49.3%, 2025=50.6%. | ✅ PASS — Runner is faithful to May 3 standalone (49.65%). Delta = 0.54 pp, within ±1 pp tolerance. |
| A3 — Shuffled-label hit rate (run_id: `20260517_020425_38cf03`) | 51.075% (808-774-33, 1,582 games). Gate_passed forced False. Notes tagged [SHUFFLE_LABELS=True]. | ✅ PASS — No leakage. Well below 52% threshold. Feature pipeline is clean. |

**Tier 1 Go/No-Go:** ❌ NO-GO — A1 fails the signal distribution test. The corrected test3 result (48.8%) shows the rushing features carry no detectable edge on real labels. Only 1/6 folds exceeds 54% and the overall result is below 50%. The previous 58.3% figure was entirely an artifact of inverted labels (predicting the opposite outcome got rewarded when labels were wrong). Infrastructure is now trustworthy (A2 and A3 both pass). The hypothesis requires reformulation before Tier 2 is warranted.

---

## Tier 2 Results

*Locked until Tier 1 Go confirmed.*

| Test | Result | Decision |
|------|--------|----------|
| A4 — Seed stability (range across 6 seeds) | (pending) | ⏳ |
| A5 — 2025 holdout hit rate | (pending) | ⏳ |
| A6 — Feature ablation (rush / 42-non-rush / union) | (pending) | ⏳ |
| A7 — Per-spread-size breakdown | (pending) | ⏳ |

**Tier 2 Go/No-Go:** ⏳ Locked

---

## Gate Outcome

*To be determined after Tier 1 and Tier 2.*

**If both tiers pass:** Tier 3 due diligence runs. PROJECT-LEAD writes a formal gate review following the format of `GATE_REVIEW_PHASE1.md`. If the experiment passes, `gate_passed = true` is set and the FRONTEND honest-evaluation banner is retired for that experiment.

**If Tier 1 fails (runner bug found in A2):** All experiment results from the config-driven runner are unreliable until the bug is fixed and A2 is re-run. This is the most severe outcome and takes priority over all other Phase 4 work.

**If Tier 1 fails (leakage detected in A3):** Begin leakage bisection. Strip feature groups one at a time, re-run the shuffle-labels test after each removal, until the shuffled hit rate falls to ~50%. The clean feature set is then used to re-run the full investigation from A1.

**If Tier 1 fails (noise concentration in A1):** The 58.3% headline is driven by one or two lucky seasons, not a stable signal. The hypothesis is not dead — rushing features may still carry edge in certain contexts — but the current result does not support a gate pass. Reformulate the experiment scope (narrower game universe, or a different fold structure) and re-run.

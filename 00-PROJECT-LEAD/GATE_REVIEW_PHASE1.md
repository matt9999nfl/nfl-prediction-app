# Phase 1 Gate Review

**Reviewed by:** PROJECT-LEAD
**Date:** 2026-05-03
**Experiment:** `20260503_110052_f6015f` (ol_xgb_v1)
**Data:** `curated.games` rebuilt and label-verified (PR-001 resolved)

---

## Gate Decision: ❌ PHASE 2 NOT CLEARED

**Required:** ≥54% ATS hit rate on ≥250 games vs. closing line
**Actual:** 48.683% ATS on 1,557 games

The sample size requirement is met by a wide margin. The hit rate requirement is not met — the result is 5.3 percentage points below the gate, with no fold clearing 51.9% and five of six folds in the 47–50% band.

This is not a close miss. The model provides 0.1 percentage points of lift over the always-home baseline (48.683% vs. 48.555%) across 1,557 games. That delta is noise.

---

## What the Results Actually Say

**The OL features are not producing edge in this configuration.** The feature importance is flat — a 0.035–0.039 range across all 29 features with no dominant signal. In a model with real predictive power, the important features stand out. Here they don't. The model has found no exploitable pattern in nflfastR-derived OL metrics alone against the closing spread.

**The OL mismatch subset is directionally interesting but statistically inconclusive.** Flag=1 (home elite OL vs. weak away defense) returned 51.6% on 64 games. Correct direction, too small to trust. Flag=2 (away elite OL) at 38.2% on 68 games is concerning — either a residual sign issue in the away composite or genuine asymmetry between home and away OL edge. At 68 games, it cannot be diagnosed confidently.

**2021 is an outlier, not a trend.** One fold at 51.9% surrounded by five folds in the 47–50% range does not indicate a seasonal pattern — it indicates variance.

**The pipeline is clean.** Raw data, curated layer, feature engineering, walk-forward harness, label derivation — all correct. The null result is a true null result, not an artifact.

---

## What This Does and Does Not Mean

**Does mean:**
- nflfastR-derived OL metrics alone, predicting all REG season games, do not produce ≥54% ATS against closing line
- The OL hypothesis as formulated — OL metrics as the primary signal across the full game universe — is not validated in this form
- Phase 2 investment (BACKEND-API, FRONTEND) is not justified at this time

**Does not mean:**
- OL performance has no relationship to game outcomes
- The hypothesis is dead
- The architecture is wrong
- The project is over

The test was narrow by design: nflfastR OL features only, predicting all games, against a 54% gate. A broader feature set, a tighter prediction threshold, or a reframed hypothesis could produce different results. We don't know yet.

---

## Hypothesis Review

Per ROADMAP.md: "If Phase 1 is not greenlit, PROJECT-LEAD convenes a hypothesis review before any Phase 2 work begins."

The core question is: **what do we test next, and does it stay within Phase 1 scope or constitute a new phase?**

Three paths are available. Decision required from project owner before any further MODELING work begins.

*(See conversation with project owner for decision.)*

---

## What Remains Locked

- BACKEND-API: no production endpoint work
- FRONTEND: no UI work
- DEVOPS: no deployment work
- Phase 2 and Phase 3: locked until a Phase 1 gate is cleared

---

## Gate Review v2 — ol_xgb_v2 (20260503_191541_a8c126)

**Date:** 2026-05-03
**Result:** 49.647% ATS on 1,557 games — gate NOT MET ❌

### What changed from v1
52 features vs 12. Added QB efficiency, explosive rates, team defense, rest/travel, form indicators. The expanded feature set produced a real but modest improvement: +0.96pp over v1. New features are contributing — pass_explosive_rate, def_epa_per_play, season_win_pct, and rolling_3wk_epa_trend all appear in the top 10.

### The signal ceiling pattern
Two experiments with substantially different feature sets (12 vs 52 features) both land in the 48.7–49.6% range with flat feature importance (0.035–0.039 in v1; 0.0177–0.0216 in v2). No feature or group dominates in either run. Best folds are 51.9% (v1) and 52.5% (v2). This is the defining pattern: the model is averaging across many equally weak signals.

The fold variance is also a problem: v2 ranges from 46.5% (2023) to 52.5% (2022). The model finds signal in some seasons and loses it in others. The 2023 fold trained on 2019–2022 did not generalize — possible regime change.

### OL mismatch subset degraded
Flag=1 dropped from 51.6% (v1) to 43.8% (v2). At 64 games this is statistically inconclusive, but the direction suggests the v1 result was noise, not signal.

### Decision pending
*(See conversation with project owner — next experiment direction required.)*

---

## ⚠️ INC-001 Notice — Config-Runner Results Invalidated

**Filed:** 2026-05-17  
**Full record:** `INC-001-label-inversion.md`

All experiment runs produced by the **config-driven runner** (`run_experiment.py`) prior to **2026-05-17 13:31 UTC** are invalidated. A label inversion in `curated.games.home_covered` caused the config runner to train and evaluate on inverted labels — models were rewarded for predicting the wrong team covered.

**Impact on Phase 1 records:**

| Run | Runner | Status |
|-----|--------|--------|
| ol_xgb_v1 `20260503_110052_f6015f` (48.68%) | Standalone (`run_phase1_backtest.py`) | ✅ Valid — computed `home_covered` inline, not from BQ |
| ol_xgb_v2 `20260503_191541_a8c126` (49.65%) | Standalone (`run_phase1_backtest.py`) | ✅ Valid — same |
| test1, test2, test3 (58–61%) | Config runner | ❌ Invalid — label-inversion artifacts |

The Phase 1 gate results (48.68% and 49.65%) are unaffected and remain the valid baseline. They were produced before the config runner was deployed. The config runner was introduced in Phase 3 (deployed 2026-05-06); the data was rebuilt with the wrong formula when the Cloud Scheduler pipeline ran after deployment.

The 10 affected rows in `experiments.backtest_runs` have been annotated with `[INC-001: labels inverted pre-2026-05-17 rebuild]` via BQ DML. INC-001 is ✅ CLOSED as of 2026-05-17.

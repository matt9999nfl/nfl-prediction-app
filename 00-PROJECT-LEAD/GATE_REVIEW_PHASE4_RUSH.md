# Phase 4 Gate Review — Rushing-Feature Hypothesis

**Reviewed by:** PROJECT-LEAD  
**Date:** 2026-05-17  
**Hypothesis:** Offensive line rushing metrics improve ATS prediction beyond the v2 baseline  
**Tier 1 decision:** ❌ NO-GO — Tier 2 locked

---

## Tier 1 Results Summary

| Check | Run ID | Result | Threshold | Status |
|-------|--------|--------|-----------|--------|
| A2 — runner faithfulness (v2 reproduction) | `20260517_020202_0504ff` | 50.190% | ≈49.65% ±1pp | ✅ PASS |
| A3 — shuffled-label leakage test | `20260517_020425_38cf03` | 51.075% | <52% | ✅ PASS |
| A1 — rush-feature experiment (test3) | `20260517_020637_245bc9` | 48.799% | ≥54% on ≥250 games, ≥4/6 folds | ❌ FAIL |

**Infrastructure verdict:** Clean. The config-driven runner is faithful to the standalone Phase 1 runner. No feature leakage detected.

**Signal verdict:** Absent on correct data. Rush features produce 48.799% ATS — 1.2 pp below the always-home baseline of ≈49.65% and 5.2 pp below the Tier 1 gate of 54%.

---

## Per-Fold Breakdown (test3, correct labels)

| Season | W | L | P | Hit Rate | Status |
|--------|---|---|---|----------|--------|
| 2020 | — | — | — | 46.5% | ❌ Below break-even |
| 2021 | — | — | — | 55.2% | ✅ Above gate |
| 2022 | — | — | — | 48.3% | ❌ |
| 2023 | — | — | — | 51.6% | 🟡 Above break-even, below gate |
| 2024 | — | — | — | 47.0% | ❌ |
| 2025 | — | — | — | 44.3% | ❌ |
| **Overall** | **772** | **810** | **33** | **48.799%** | ❌ NO-GO |

Gate requires ≥4 of 6 folds at or above 54%. Only 1 fold cleared that threshold (2021 at 55.2%). The remaining folds are scattered across the 44–52% range with no directional consistency.

---

## Context: INC-001 and the Pre-Fix Results

The original rushing-feature experiments (test1, test2, test3) reported hit rates of 58–61%. These results triggered Phase 4 and were the impetus for this Tier 1 investigation.

All three were produced by the config-driven runner reading from `curated.games.home_covered`, which contained an inverted label at the time. The model was trained and evaluated on a target where underdogs "covered" 86.8% of the time and heavy favourites "covered" 6.3% of the time. It found a real pattern — but the pattern was in the inverted labels, not in ATS outcomes.

After INC-001 was remediated (DATA-PIPELINE fixed `derive_home_covered`, rebuilt all seasons, spread-bin diagnostic confirmed all buckets at 45–55%), MODELING re-ran all three Tier 1 experiments on correct labels. The pre-fix results are not close calls that became misses. They were entirely artifacts of the inversion. The post-fix results are:

- Runner faithfulness (A2): 50.19% — the runner works correctly
- Leakage test (A3): 51.07% — no feature pipeline leakage
- Rush-feature model (test3): 48.80% — no detectable edge

INC-001 is ✅ CLOSED. Full record in `INC-001-label-inversion.md`.

---

## What This Result Means

**The rushing hypothesis as formulated is not validated.**

The hypothesis was: offensive line rushing EPA-per-attempt metrics, added to the v2 feature set, would improve ATS hit rates above the break-even threshold of ~52.38% and ideally above the 54% gate.

On correct labels, these features provide no detectable improvement. The model's overall hit rate (48.80%) is below the v2 baseline (50.19%), suggesting the rushing features may be adding noise rather than signal.

**The infrastructure hypothesis IS validated.** This was a secondary Tier 1 goal: confirm the config-driven runner is faithful to the Phase 1 standalone runner. It is (A2: +0.54pp from target, well within the ±1pp tolerance). The experiment platform works correctly.

---

## What This Does Not Mean

- That rushing performance is irrelevant to game outcomes
- That OL metrics cannot contribute to a model
- That the nflfastR data is wrong
- That the project should stop

A single feature-set experiment on a single hypothesis is a narrow test. The infrastructure is clean and the backtest framework is validated. The question is what feature set and what hypothesis to test next.

---

## Tier 2 Status

Locked. Tier 1 Go/No-Go criteria were not met. There is no signal to validate further at this time.

---

## Options for Next Hypothesis

The following are directions available for consideration. This is not a recommendation — it is a menu. Decision required from project owner.

**Option A — Reformulate the rushing hypothesis more narrowly.**  
Test rush features only in a targeted game universe: games where rushing volume is anomalously high (weather, opponent pass defense rank), or games with significant OL lineup changes between the spread-setting date and kickoff. The current experiment predicts all regular-season games — a more surgical application might surface edge that gets averaged away in the full universe.

**Option B — Pivot to a market-structure hypothesis.**  
The most robust ATS signals in the academic literature relate to market behavior: public betting percentages, line movement, home-field value by opponent familiarity. These require external data (betting-market feeds) not currently in the pipeline, but they represent a distinct and well-researched hypothesis class.

**Option C — Pivot to a situational hypothesis.**  
Filter the game universe rather than change the feature set. Examples: divisional games, primetime games, short-week games, playoff-positioning games in Weeks 15–18. If the model finds edge in a subset, that's exploitable even if the full-universe result is flat.

**Option D — Invest in feature engineering depth before new experiments.**  
The current feature set is clean but shallow — mostly per-game aggregates. Introduce rate-normalized, opponent-adjusted, and line-movement features before running new experiments. This is slower but produces richer signal candidates.

---

## Decision Required

Project owner must choose a direction before MODELING begins any new experiment design or data work. The current backlog is clear:

- MODELING has no active experiment queue
- DATA-PIPELINE has no open remediation work
- Infrastructure is clean and deployed

This is a clean decision point, not a forced choice under technical pressure.

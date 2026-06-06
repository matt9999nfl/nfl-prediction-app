# Rush-Feature Experiments — Project Lead Review

**Reviewer:** PROJECT-LEAD
**Date:** 2026-05-16
**Subject:** test1 / test2 / test3 experiments — 10 rushing-based features producing 58–61% ATS results

---

## TL;DR

These three experiments report ATS hit rates of **58.3% – 61.4%** using 10 rushing-based features over a walk-forward backtest. **The result is in direct tension with the May 3 gate review**, which concluded that no nflfastR-derived feature configuration produced ≥54% ATS against the closing line. The 6-fold walk-forward with 52 features (`20260503_191541_a8c126`) hit **49.65%** on the *same* train/test windows that test3 is now reporting **58.32%** on.

The walk-forward harness, feature engineering, and label derivation all read clean — I cannot find a leakage bug. But the magnitude of the lift (+9 pp from removing 42 features) is large enough that I do not believe the result without further validation. **Do not promote any of these to a "framework" until at least the per-fold breakdown, shuffled-label test, and v2-feature reproduction below have been run.**

---

## What the experiment process is doing

For each "Run" in the UI, the runner (`run_experiment.py`) executes:

1. Loads `curated.plays` and `curated.games` from BigQuery (all seasons 2015–2025).
2. Computes 23 per-team weekly features in a season-to-date rolling window. Critically, this uses `cumsum() − current_week_value` so the feature for "Team X going into Week W" only reflects plays from Weeks 1..W−1.
3. Selects the 10 columns requested by the config; adds the 6 game-context features that the runner always appends (`home_advantage, div_game, roof_dome, temp, wind, rest_differential`). Total model features = 16.
4. Runs a walk-forward backtest with folds derived from `start_season, end_season, train_seasons`:
   - test1 (2020–2024, train=4) → **1 fold**: train 2020–2023, test 2024
   - test2 (2016–2020, train=4) → **1 fold**: train 2016–2019, test 2020
   - test3 (2016–2025, train=4) → **6 folds**: tests 2020, 2021, 2022, 2023, 2024, 2025
5. Per fold: fits StandardScaler + mean imputer + XGBoost (`OLXGBModelV2`, fixed `random_state=42`) on training-only data, predicts on test season. A prediction is "correct" if `P(home covers) > 0.5` matches `home_covered`. Pushes excluded from denominator.
6. Aggregates wins / (wins + losses) across all fold test seasons to produce the dashboard hit rate.

---

## Why test1 and test2 should be discarded

Both are **single-fold experiments**. They use the `build_folds_from_config` walker which produces only one fold whenever `end_season − start_season = train_seasons`. Single-fold ATS results have ~3 pp standard error on ~270 games and routinely swing 8–10 pp between adjacent seasons for the same model — they are not robust evidence of edge. The 251 / 272 game counts also barely clear the 250-game min-sample gate, which makes the gate near-meaningless for these configs.

Only **test3** is a legitimate walk-forward result, and even there only one fold (F5 = 2024, 61.4%) is visible in the screenshot.

---

## Why the test3 result is suspicious

Same fold structure as the May 3 v2 backtest (2019–2024 was the prior v2 set; test3 evaluates 2020–2025, so 5 of 6 folds overlap). Same walk-forward harness. Same `OLXGBModelV2` class with the same fixed seed. The May 3 v2 per-season results (from the local CSV `20260503_191541_a8c126_by_season.csv`):

| Season | v2 (52 features) | Implied from test3 / test1 |
|---|---|---|
| 2019 | 47.15% | (not in test3 window) |
| 2020 | 52.34% | F1 (unknown — not in screenshot) |
| 2021 | 50.00% | F2 (unknown) |
| 2022 | 52.49% | F3 (unknown) |
| 2023 | 46.51% | F4 (unknown) |
| 2024 | 49.25% | **F5 = 61.40%** ✅ visible |
| 2025 | — | F6 (unknown) |

The 2024 fold jumped from 49.25% to 61.40% by removing 42 features. That gap is much larger than typical "feature reduction helps" magnitudes (1–3 pp in small-n regimes). The May 3 gate review explicitly noted that feature importance was *flat* across all 52 features with no rushing feature standing out as dominant signal — making this dramatic improvement from a rushing-only subset more suspicious, not less.

Possible benign explanations: the 52-feature model was overfitting to noise and the smaller feature set has less variance; rushing genuinely has signal that's drowned out when combined with noisy passing features; the runner went through a slightly different code path that happens to be cleaner.

Possible non-benign explanations: a data change between May 3 and May 9; a subtle behavior difference in `build_feature_matrix` (the new config-driven path) vs `run_phase1_backtest.py` (the old standalone path); concentration of correct predictions in one season inflating the headline number.

---

## What the result would mean if it holds up

A 58.3% ATS hit rate over 1,591 games is, if real, an enormous edge — sharp professional NFL bettors typically aim for 53–55% long-term, and 58% would be on the order of historically best-documented betting models. At -110 odds, breakeven is 52.38%, so 58% implies ~11% ROI per bet. The economic interpretation would be that closing lines systematically underweight rushing-game leverage relative to passing/QB signals — a behaviorally plausible inefficiency given how heavily public attention skews toward passing — but this is a strong claim that requires strong evidence.

A 58.3% ATS hit rate over 1,591 games is, if not real, almost certainly explained by either (a) one or two fold-seasons carrying the average and the others sitting near 50%, or (b) an undetected leakage or implementation bug in the new runner path that didn't exist in the standalone backtester used for the v2 baseline.

---

## Validation plan (ordered by diagnostic value vs. effort)

### Tier 1 — run these first (1 afternoon total)

1. **Pull the full per-fold breakdown for test3.** The dashboard shows only F5. Fetch `experiments.backtest_predictions` filtered to the test3 run_id and group by season → hit rate. If five folds are 53–57% and one is 70%, the headline is fragile. If all six are 56–60%, the signal is much more credible.

2. **Reproduce the v2 (52-feature) result through the new runner.** Create a framework experiment listing all 52 v2 features, run it through the config-driven path, and compare against the May 3 standalone result (49.65%). If the new runner returns ~49.65%, the runner is faithful and the rushing-only result is genuinely from feature selection. If it returns something else, the bug is in the new runner.

3. **Shuffled-label test.** Re-run test3 with `home_covered` randomly permuted within each season *before* the train/test split (within season to preserve the same push rate). If the model still produces ≥55%, there is leakage somewhere. If it collapses to ~50%, leakage is ruled out and the 58.3% is genuine model output, not data leakage.

### Tier 2 — run if Tier 1 doesn't kill the result

4. **Random-seed stability.** Re-run test3 with seeds {1, 7, 99, 314, 2024}. Hit rate stable within ±2 pp → signal is robust. Swings of 5+ pp → seed-lottery effect.

5. **Out-of-sample 2025 holdout.** Train on 2020–2024 only, predict 2025 cold. If the model holds 56%+ on a season nobody touched during exploration, the prior result is more believable. If it drops to ~51%, prior results were partially in-sample artifacts.

6. **52-features-plus-rush ablation.** Run a config with the 52 v2 features. Then run one with only the 10 rush features. Then run one with both feature sets unioned. Where the union lands tells you whether the rush features add edge *to* the v2 set or whether the gain is really about removing the other 42.

7. **Per-spread-size slice.** Compute hit rate separately for spreads in (0, 3], (3, 7], (7, 10], (10+). Edge concentrated in large spreads is a known efficient-market quirk for blowout games, often not tradeable. Edge spread evenly across spread sizes is much more believable.

### Tier 3 — pre-production due diligence

8. **Calibration plot.** P(home covers) bin vs. actual home cover rate in 10 bins. Real-edge models track the 45-degree line; quirk-models often show one bin doing all the work.

9. **Permutation feature importance.** Permute each of the 10 features and measure the hit-rate drop. If one feature accounts for 80% of the lift, the model is brittle and probably won't survive line moves or rule changes.

10. **Closing-line-only vs. opening-line.** Re-evaluate against opening lines if available. A model that beats closing -110 is real edge; a model that only beats opening lines but loses at close is just slower than the market.

---

## Recommendation

Do not promote any of these three experiments to a "framework," do not present 58.3% as a working result externally, and do not start building anything that depends on this hit rate being real until at least Tier 1 (#1–#3) has been completed. The most likely outcomes after Tier 1 are:

- **#1 reveals one or two outlier folds** → most of the apparent edge is concentrated noise; rerun with a longer evaluation window and the average will regress toward 51–53%.
- **#2 fails to reproduce 49.65%** → there's a bug in the new config-driven runner that doesn't exist in `run_phase1_backtest.py`. Find it and re-run everything once it's fixed.
- **#3 shows ≥55% on shuffled labels** → leakage somewhere. Bisect by stripping out feature builders one at a time until the shuffled-label hit rate falls to 50%.
- **All three pass cleanly** → the rushing-feature edge is real, the May 3 gate review's conclusion needs to be revisited, and Tier 2 / Tier 3 due diligence becomes the priority before any betting / production use.

The fastest path to either confirming or killing this result is steps 1, 2, and 3 above. They can be done in one work session by MODELING.

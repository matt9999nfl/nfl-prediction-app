# HANDOFF — Week 1/2 pick-explanation analysis, 2026-09-18

**Goal achieved: yes.** Every acceptance line in `PROMPT-WEEK1-ANALYSIS.md` is true (checked below).

**Covers:** `PROMPT-WEEK1-ANALYSIS.md` (Stage 2 of `PROMPT-PICK-EXPLANATIONS-AND-EDGE-LAB.md`). Analysis only — no model built, no production behaviour changed, nothing written to BigQuery.

---

## Commit

| Commit | What |
|---|---|
| `80cd3b6` | `02-MODELING/backtests/analyze_week_explanations.py` (+ tests) and both week reports |

Pushed to `main`? **Not pushed** — committed locally only, per the standing rule of not pushing without being asked.

## Reports

| Path | |
|---|---|
| `02-MODELING/backtests/reports/week_analysis_2026_wk01.md` | Week 1 — 16 games |
| `02-MODELING/backtests/reports/week_analysis_2026_wk02.md` | Week 2 — 16 games, results left empty (week in progress) |
| `..._wk01_{drivers,family_push_stats,clusters,family_spread_correlation,games}.csv` | Data behind each week-1 section |
| `..._wk02_{drivers,family_push_stats,clusters,family_spread_correlation,games}.csv` | Same, week 2 |

## Run IDs the explanations came from

Same rule the API uses (exact over approximate, then newest `created_at`) — the script selects one run per game, same as `app/queries/explanations.py`:

| Season/week | run_id | Games | Note |
|---|---|---|---|
| 2026 wk 1 | `7ddd6dda-f410-404e-b29c-3158583ebb3c` | 16 | `is_approximate=true`, max diff 0.0370 |
| 2026 wk 2 | `82abf4e0-bab6-47ea-b5a9-4d1e6abc6e46` | 16 | exact reproduction |

## What the script does

`analyze_week_explanations.py --season S --week N`:

1. Reads `experiments.prediction_explanations` for the week (same best-run-per-game rule as the API).
2. Reads the live served pick, closing spread and result from `experiments.backtest_predictions`.
3. Re-signs every feature's contribution toward the **live served pick** — exactly like the API's live-pick authority — and flags `side_mismatch` for any game whose underlying explanation run leans the other way.
4. Builds, per game: top-5 drivers, family matchup view, top-1/top-3 family share of total |contribution|, imputed/weather/roof_dome call-outs, and a templated two-sentence summary.
5. Builds, across the week: mean |contribution| and "pushed toward the pick" frequency per family (given both over all games and excluding side-mismatches), hierarchical clustering of games by family-level pick-direction vector (cosine distance, average linkage), and recurring top-driver "shapes" (family + side of each game's #1 driver).
6. Builds the market section: P(cover) vs. closing spread sorted by disagreement, underdog-pick family behaviour, behaviour near the 3/7 key numbers, line-snapshot coverage, moneyline de-vig (checked per-week, not assumed from season totals), and per-family correlation with the closing spread.
7. Ends with numbered, data-grounded hypotheses for the next stage.
8. Kill-switches: exits non-zero (writing nothing) if fewer than 16 games have explanations, or if any game's contributions don't reconstruct its stored probability within 1e-4.

## Findings worth flagging before the next stage reads the reports

- **Week 1**: 3 side-mismatch games (`2026_01_ATL_PIT`, `2026_01_GB_MIN`, `2026_01_NYJ_TEN`) — confirmed to match the set already recorded in `HANDOFF-2026-09-18-stage1-finish.md`. 2 after-kickoff regenerations (`2026_01_NE_SEA`, `2026_01_SF_LA`). `2026_01_NE_SEA` is a push (`home_covered` is `NULL` because the margin exactly equalled the spread, not because it hasn't been played) — the script distinguishes this from "not yet played" using `curated.games.home_score`/`away_score`.
- **`raw_lines.line_snapshots` is empty** — 0 rows for either week. The market section states this rather than reporting a fabricated "0 of 16" as if snapshots had run and found nothing; snapshot capture (`01-DATA-PIPELINE/scripts/snapshot_lines.py`) has evidently not executed yet against a live slate.
- **Moneylines**: `raw_nflfastr.schedules` has `home_moneyline`/`away_moneyline` populated for exactly the 32 week-1/week-2 2026 games (0 elsewhere in 2026) and for all of 2015–2025. De-vigged market probability is shown for both weeks.
- **Interaction values**: not stored anywhere in `experiments.prediction_explanations` (no interaction columns in the schema) — every game section says so plainly rather than reporting a blank.
- No games were regenerated after kickoff in week 2; no side-mismatches in week 2.

## Tests

| | Before | After |
|---|---|---|
| Modeling (`02-MODELING`, pytest, full suite) | 221 | 239 |

18 new tests in `test_analyze_week_explanations.py`, covering: pick-direction re-signing with and without a side mismatch (and that it raises on an unmatched game), that side-mismatched games are excluded from the 13-game "toward the pick" aggregate while both counts are still reported, top-driver ordering by |pick-direction-toward-live-pick|, the reconstruction-tolerance check (pass and fail cases), favourite/underdog and key-number helpers, moneyline de-vig arithmetic, and a guard against clustering an all-zero family vector. All green; no BigQuery calls in the test suite.

## Hand-off hypothesis list (copied in full)

### Week 1

1. Picks where coverage/defence other is the top driver and it pushed toward the pick (true in 85% of the 13 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
2. Picks where QB is the top driver and it pushed toward the pick (true in 77% of the 13 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
3. OL run blocking correlates most with the closing spread (r=-0.53) and is largely repeating the market — test whether excluding it from the feature set changes backtest log loss.
4. QB correlates least with the closing spread (r=0.01) — test whether picks driven by this family beat the market ATS on 2015-2025, independent of the spread.
5. Picks where the model backs the underdog and QB is the top driver — test ATS performance on 2015-2025 for underdog picks split by this family's direction.
6. Games whose #1 driver is QB on the away side (5 of this week's games) — test whether this shape recurs and beats the market ATS on 2015-2025.
7. Games within half a point of the 3 or 7 key numbers — test whether the model's calibration (P(cover) vs. actual cover rate) differs near these numbers on 2015-2025.

### Week 2

1. Picks where OL run blocking is the top driver and it pushed toward the pick (true in 75% of the 16 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
2. Picks where run game is the top driver and it pushed toward the pick (true in 75% of the 16 non-mismatched games) — test ATS performance on 2015-2025 for games where this family is the #1 driver.
3. record/margin correlates most with the closing spread (r=0.70) and is largely repeating the market — test whether excluding it from the feature set changes backtest log loss.
4. rest correlates least with the closing spread (r=-0.00) — test whether picks driven by this family beat the market ATS on 2015-2025, independent of the spread.
5. Picks where the model backs the underdog and QB is the top driver — test ATS performance on 2015-2025 for underdog picks split by this family's direction.
6. Games whose #1 driver is QB on the home side (4 of this week's games) — test whether this shape recurs and beats the market ATS on 2015-2025.
7. Games within half a point of the 3 or 7 key numbers — test whether the model's calibration (P(cover) vs. actual cover rate) differs near these numbers on 2015-2025.

## Acceptance check

- [x] `reports/week_analysis_2026_wk01.md` exists, section for each of 16 `game_id`s; `week_analysis_2026_wk02.md` for all 16 week-2 games.
- [x] Approximate caveat, 3 side-mismatch games, 2 after-kickoff games each named at the top of the week-1 report.
- [x] Every "toward the pick" statistic given on the non-mismatched-game count and on all games (both counts shown per row/cell; week 1 = 13/16, week 2 = 16/16 since it has no mismatches).
- [x] Each game section lists 5 drivers with family, stat name, raw value, league percentile, signed contribution.
- [x] Patterns section names each group (by dominant families), its games.
- [x] Market section states which moneyline seasons/weeks are populated, and how many week games have a first-seen line in `line_snapshots` (0 for both — table is empty, stated plainly).
- [x] Per-family correlation table with the closing spread present, all 16 games, both weeks.
- [x] Report ends with 7 numbered testable hypotheses (both weeks).
- [x] Script runs for any (season, week) with stored explanations (parameterised, no hardcoded week-1 assumptions in the core logic); tests cover the pick-direction sign and the side-mismatch exclusion; test counts given above (221 → 239).

## Not done / out of scope this stage

Per the prompt's Scope section: only `analyze_week_explanations.py`, its test, and `reports/**` were touched. No other code, no BigQuery table, no job/schedule, no stored picks or explanations were changed. "Generate predictions" was not run.

## Left open

- `raw_lines.line_snapshots` capture has apparently not run against a live slate yet (table is empty) — worth checking whether the pipeline step is scheduled at all; the market section's line-movement analysis is currently a stated limitation rather than real coverage.
- The moneyline de-vig comparison is shown side by side with P(home cover) but is explicitly not equated (different underlying bets: straight-up win vs. ATS cover) — a market-implied ATS probability would need the spread odds (`home_spread_odds`/`away_spread_odds`), which `snapshot_lines.py` captures but which aren't in `curated.games` or `backtest_predictions`; not pulled in this stage since it wasn't asked for.

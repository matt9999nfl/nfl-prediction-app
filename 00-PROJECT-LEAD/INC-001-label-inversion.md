# INC-001 — Label Inversion in `curated.games.home_covered`

**Severity:** Critical — all config-runner experiment results are invalid  
**Filed:** 2026-05-17  
**Filed by:** PROJECT-LEAD (triggered by MODELING Tier 1 investigation, Phase 4)  
**Status:** ✅ CLOSED  
**Blocking:** Phase 4 Track 1 (model validation). Does not block Track 2 or Track 3.

---

## What Happened

MODELING ran the Phase 4 Tier 1 runner faithfulness check (A2): a 52-feature experiment through the config-driven runner targeting ≈49.65% to match the May 3 standalone result. The runner returned **68.74%** — a 19 pp gap. The spread-bin diagnostic confirmed the root cause immediately:

| Spread bucket | Observed cover rate | Expected (efficient market) |
|---|---|---|
| Heavy underdog (home) | **86.8%** | ~48–52% |
| Heavy favourite (home) | **6.3%** | ~48–52% |

This is an unmistakable label inversion: the `home_covered` column in `curated.games` is assigning `True` to the wrong team.

The shuffled-label test (A3) returned 51.1% — no leakage in the feature pipeline itself. The inversion is in the data, not in the feature builders.

---

## Root Cause

The bug is in `01-DATA-PIPELINE/scripts/build_curated_games.py`, function `derive_home_covered`:

**Current (buggy) code:**
```python
required_margin = -home_spread_close   # ← sign is wrong
covered[both_valid & (margin > required_margin)] = True
```

**What this produces:**  
When the home team is favored by 7 (`home_spread_close = 7`), `required_margin = -7`. The condition `margin > -7` is true for any home margin greater than -7, meaning a home team that loses by 6 is marked as having covered a -7 spread. That is incorrect — a home -7 favourite must win by more than 7 to cover.

**Correct formula:**  
nflverse stores `spread_line` as positive = home favoured (confirmed in PR-001, 2026-05-03). The correct condition is:

```python
required_margin = home_spread_close    # no negation
covered[both_valid & (margin > required_margin)] = True
```

This makes `home_covered = True` when `home_score - away_score > home_spread_close`, i.e. when the home team's margin exceeds what they were giving.

**Why this is a recurrence:**  
PR-001 (2026-05-03) fixed this same inversion in the data at the time. The fix was either not committed to `build_curated_games.py`, or was overwritten when DATA-PIPELINE ran a full rebuild (the Cloud Scheduler pipeline runs weekly per Phase 3 DEVOPS). The standalone `run_phase1_backtest.py` computed `home_covered` inline and got it right; the config-driven runner reads from the pre-computed `curated.games` table and inherited the stale, broken value.

---

## Impact

| Artifact | Status |
|---|---|
| `curated.games.home_covered` (all seasons 2015–2025) | ❌ Inverted — must be rebuilt |
| test1, test2, test3 experiment results | ❌ Invalid — all based on inverted labels |
| Phase 4 Track 1 A2 run (52-feature faithfulness check) | ❌ Invalid (68.74%) |
| Phase 4 Track 1 A3 run (shuffled-label test, 51.1%) | ✅ Valid as a pipeline architecture check (no feature leakage) — but must be re-run after label fix |
| May 3 standalone runs (ol_xgb_v1 48.7%, ol_xgb_v2 49.65%) | ✅ Valid — standalone runner computed home_covered inline, not from BQ |
| All `experiments.backtest_predictions` rows from config runner | ❌ Invalid — correct column values in the record, but the `correct` column reflects inverted labels |

---

## Required Actions

**DATA-PIPELINE (primary):**
1. Fix `derive_home_covered` in `build_curated_games.py` — remove the negation on `home_spread_close`
2. Rebuild `curated.games` for all seasons (2015–2025)
3. Run the spread-bin diagnostic on the rebuilt table and confirm favorites cover ≈48–52% and underdogs cover ≈48–52%
4. Annotate all invalidated rows in `experiments.backtest_runs` — add a note to each config-runner run identifying them as pre-fix
5. Document the fix in `PIPELINE_REMEDIATION_002.md`

**MODELING (after DATA-PIPELINE confirms clean rebuild):**
1. Re-run A2 (52-feature faithfulness check) — should return ≈49.65%
2. Re-run A3 (shuffled-label test) — confirm still ≈50%
3. Re-run test3 (rush-feature experiment) — this produces the number we actually care about
4. Resume Tier 1 Go/No-Go with correct results

**PROJECT-LEAD:**
1. ✅ Once DATA-PIPELINE confirms fix, update this incident to 🟡 RESOLVED — PENDING RERUN
2. ✅ Once MODELING confirms A2 ≈ 49.65%, update to ✅ CLOSED — confirmed 2026-05-17 (A2 = 50.19%)
3. ✅ Update `GATE_REVIEW_PHASE1.md` to note that all config-runner runs prior to this fix are invalidated

---

## Prevention

The pipeline rebuild (Cloud Scheduler, weekly) can re-introduce this bug if the script is wrong at run time. The fix must go into the script, not just into the data. After this incident closes:

- Add a spread-bin sanity check to `validate_and_report.py` (or equivalent): assert that the cover rate in the `(0, 3]` spread bucket is between 46% and 54%. If it's outside that range, alert and do not write to `curated.games`. This would have caught this regression automatically.
- Add the same check to the TESTING-QA no-lookahead test suite (`test_no_lookahead.py`) as a data quality gate on CI.

---

## Timeline

| Time | Event |
|------|-------|
| 2026-05-03 | PR-001 filed and resolved — `home_covered` sign convention fixed in data |
| 2026-05-03 | Standalone runner (run_phase1_backtest.py) produced 49.65% — correct |
| 2026-05-06 | Config-driven runner (run_experiment.py) delivered — reads from curated.games |
| 2026-05-07 | Phase 3 deployment complete — weekly pipeline scheduler activated |
| 2026-05-09 | test3 rush-feature experiment run — config runner produces 58.3% (inverted labels) |
| 2026-05-17 | MODELING Tier 1 A2 produces 68.74% — inversion diagnosed |
| 2026-05-17 | INC-001 filed — DATA-PIPELINE remediation initiated |
| 2026-05-17 | `derive_home_covered` fixed in `build_curated_games.py` (removed negation on `home_spread_close`) |
| 2026-05-17 | `curated.games` rebuilt for all seasons 2015–2025 — all OK |
| 2026-05-17 | Spread-bin diagnostic confirms fix — all 5 buckets 45–55% (home_dog_10+=50.8%, home_dog_3-10=47.5%, home_fav_10+=54.4%, home_fav_3-10=50.7%, pick_em=47.6%) |
| 2026-05-17 | Cover-rate sanity check added to `validate_and_report.py` (section 3b) |
| 2026-05-17 | 10 rows in `experiments.backtest_runs` annotated with INC-001 label |
| 2026-05-17 | `PIPELINE_REMEDIATION_002.md` written — INC-001 status updated to RESOLVED — PENDING MODELING RERUN |
| 2026-05-17 | MODELING Tier 1 rerun complete: A2=50.19% ✅, A3=51.07% ✅, test3=48.80% ❌ NO-GO — INC-001 ✅ CLOSED |

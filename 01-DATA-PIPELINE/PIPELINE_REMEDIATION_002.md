# PIPELINE_REMEDIATION_002 — INC-001 Label Inversion Fix

**Date:** 2026-05-17  
**Incident:** INC-001 — `curated.games.home_covered` label inversion  
**Severity:** Critical  
**Agent:** DATA-PIPELINE  
**Status:** ✅ Fixed and verified  

---

## What Was Wrong

The function `derive_home_covered` in `01-DATA-PIPELINE/scripts/build_curated_games.py` had an inverted sign on the spread condition:

**Buggy code (pre-fix):**
```python
required_margin = -home_spread_close   # sign is wrong
covered[both_valid & (margin > required_margin)] = True
```

nflverse stores `spread_line` as positive = home favoured (e.g. `home_spread_close = 7` means the home team is a 7-point favourite and must win by more than 7 to cover). With the negation, a home -7 favourite had `required_margin = -7`, so the condition `margin > -7` was satisfied by any home margin greater than -7 — including losses by 1 through 6. This marked a home team that lost by 6 as having "covered" a -7 spread. The result was a full inversion: home underdogs appeared to cover at 86.8% and home favourites at 6.3%.

The bug was not present in the standalone `run_phase1_backtest.py`, which computed `home_covered` inline using the correct formula. It was present in `build_curated_games.py`, which feeds the `curated.games` table that the config-driven runner (`run_experiment.py`) reads. This explains why the Phase 1 standalone results (48.7%, 49.65%) were valid but all config-runner experiment results were not.

**Root cause of recurrence:** PR-001 (2026-05-03) fixed the sign in the data at that time, but the fix was either not committed to `build_curated_games.py`, or was overwritten when DATA-PIPELINE ran a full rebuild after the weekly Cloud Scheduler pipeline activated (Phase 3 DEVOPS, 2026-05-07).

---

## What Was Fixed

**File:** `01-DATA-PIPELINE/scripts/build_curated_games.py`  
**Function:** `derive_home_covered`

**Change:**
```python
# Before (wrong):
required_margin = -home_spread_close

# After (correct):
required_margin = home_spread_close
```

The docstring was also corrected from:
```
home_covered = True  if (home_score - away_score) > -home_spread_close
```
to:
```
home_covered = True  if (home_score - away_score) > home_spread_close
```

An expanded docstring was added explaining the nflverse sign convention.

---

## Rebuild

`curated.games` was rebuilt for all seasons 2015–2025 on 2026-05-17:

```
cd C:\Users\Matth\Desktop\nfl-prediction-app\01-DATA-PIPELINE
C:\Users\Matth\AppData\Local\Programs\Python\Python311\python.exe scripts/build_curated_games.py
```

All 11 seasons loaded successfully:

| Season | Rows | Status |
|--------|------|--------|
| 2015 | 256 | OK |
| 2016 | 256 | OK |
| 2017 | 256 | OK |
| 2018 | 256 | OK |
| 2019 | 256 | OK |
| 2020 | 256 | OK |
| 2021 | 272 | OK |
| 2022 | 271 | OK |
| 2023 | 272 | OK |
| 2024 | 272 | OK |
| 2025 | 272 | OK |

---

## Verification — Spread-Bin Diagnostic

The following query was run against `nfl-model-471509.curated.games` after the rebuild:

```sql
WITH bins AS (
  SELECT
    CASE
      WHEN home_spread_close <= -10 THEN 'home_fav_10+'
      WHEN home_spread_close <= -3  THEN 'home_fav_3-10'
      WHEN home_spread_close < 3    THEN 'pick_em'
      WHEN home_spread_close < 10   THEN 'home_dog_3-10'
      ELSE                               'home_dog_10+'
    END AS bucket,
    home_covered
  FROM `nfl-model-471509.curated.games`
  WHERE season BETWEEN 2015 AND 2025
    AND home_covered IS NOT NULL
)
SELECT
  bucket,
  COUNTIF(home_covered) AS covers,
  COUNT(*) AS total,
  ROUND(100 * COUNTIF(home_covered) / COUNT(*), 1) AS cover_pct
FROM bins
GROUP BY bucket
ORDER BY bucket
```

**Results (post-fix):**

| Spread Bucket | Covers | Total | Cover % | In Range? |
|---------------|--------|-------|---------|-----------|
| home_dog_10+  | 135    | 266   | 50.8%   | ✅ (45–55%) |
| home_dog_3-10 | 532    | 1,120 | 47.5%   | ✅ (45–55%) |
| home_fav_10+  | 43     | 79    | 54.4%   | ✅ (45–55%) |
| home_fav_3-10 | 349    | 689   | 50.7%   | ✅ (45–55%) |
| pick_em       | 318    | 668   | 47.6%   | ✅ (45–55%) |

All buckets are within the 45–55% efficient-market expectation. The pre-fix values were `home_dog_10+` at 86.8% and `home_fav_10+` at 6.3% — a definitive inversion. The fix is confirmed clean.

---

## Prevention

A cover-rate sanity check was added to `scripts/validate_and_report.py` (new section 3b). It:

1. Queries all five spread buckets and asserts each falls between 45% and 55%.
2. Queries the overall cover rate across all seasons and asserts it falls between 46% and 54%.
3. Fails loudly with a clear error message if any bucket is out of range, identifying the affected season span.
4. References this document and INC-001 in the error message for context.

This check will fire on every validation run, catching any future regression (e.g. if the weekly Cloud Scheduler overwrites the script with a broken version again).

The instructions file (`instructions.md`) already documented the required semantic distribution check and the 45–55% per-bucket requirement. The `validate_and_report.py` addition enforces it automatically going forward.

---

## Experiments Invalidated

All config-driven backtest runs in `experiments.backtest_runs` created before 2026-05-17 are invalid. These experiments read `home_covered` from `curated.games`, which contained inverted labels.

Affected experiments are identified by `experiment_config_id IS NOT NULL AND created_at < '2026-05-17'`. A DML UPDATE was run on 2026-05-17 to annotate all affected rows (see BQ Annotation section below).

| Experiment | Status |
|---|---|
| test1, test2, test3 config-runner runs | ❌ Invalid — labels inverted |
| Phase 4 A2 run (68.74%) | ❌ Invalid — labels inverted |
| Phase 4 A3 shuffled-label run (51.1%) | ✅ Valid as architecture check — no feature leakage; must be re-run on correct labels |
| May 3 standalone runs (ol_xgb_v1 48.7%, ol_xgb_v2 49.65%) | ✅ Valid — computed home_covered inline, not from BQ |

**Experiments that must be re-run (MODELING):**
1. A2 — 52-feature faithfulness check (target: ≈49.65%)
2. A3 — shuffled-label test (target: ≈50%)
3. test3 — rush-feature experiment (this is the result MODELING actually cares about)

---

## BQ Annotation

The following DML was run on 2026-05-17 to mark all invalidated config-runner experiments:

```sql
UPDATE `nfl-model-471509.experiments.backtest_runs`
SET notes = CONCAT(COALESCE(notes, ''), ' [INC-001: labels inverted pre-2026-05-17 rebuild]')
WHERE experiment_config_id IS NOT NULL
  AND created_at < '2026-05-17'
```

The two Phase 1 standalone runs (`experiment_config_id IS NULL`) were not touched.

---

## Timeline

| Time | Event |
|------|-------|
| 2026-05-03 | PR-001 filed and resolved — sign convention fixed in data at the time |
| 2026-05-03 | Standalone runner (run_phase1_backtest.py) produced 49.65% — correct |
| 2026-05-06 | Config-driven runner (run_experiment.py) delivered — reads from curated.games |
| 2026-05-07 | Phase 3 deployment complete — weekly pipeline scheduler activated |
| 2026-05-09 | test3 rush-feature experiment run — config runner produces 58.3% (inverted labels) |
| 2026-05-17 | MODELING Tier 1 A2 produces 68.74% — inversion diagnosed via spread-bin diagnostic |
| 2026-05-17 | INC-001 filed — DATA-PIPELINE remediation initiated |
| 2026-05-17 | `derive_home_covered` fixed in `build_curated_games.py` |
| 2026-05-17 | `curated.games` rebuilt for all seasons 2015–2025 — all OK |
| 2026-05-17 | Spread-bin diagnostic confirms fix — all buckets 45–55% |
| 2026-05-17 | Cover-rate sanity check added to `validate_and_report.py` |
| 2026-05-17 | Invalidated BQ rows annotated in `experiments.backtest_runs` |
| 2026-05-17 | INC-001 status updated to RESOLVED — PENDING MODELING RERUN |
